# planning.md

## Detection signals

What are your 2+ signals?

-   LLM-based classification (Groq): semantic and stylistic coherence
-   Stylometric heuristics: measurable statistical properties

**What does each signal measure?**

- **LLM-based classification (Groq):** Measures holistic semantic and stylistic coherence — how predictable, well-structured, and tonally consistent the text is at the sentence and paragraph level. AI-generated text tends to produce high-probability, lexically smooth prose with consistent register and well-formed transitions; human writing introduces idiosyncratic phrasing, tonal shifts, incomplete thoughts, and personal tangents that lower predictability. What it *can't* capture: it will not reliably detect AI text that was explicitly prompted to sound informal or conversational, and it may misclassify highly polished human writing (e.g. professional copy) as AI-generated. It is also opaque — there is no decomposable reason for its score beyond what the model volunteers in its reasoning.

- **Stylometric heuristics:** Measures four statistical surface properties: (1) sentence length variance — AI writing tends to produce sentences of more uniform length; (2) type-token ratio (TTR) — vocabulary diversity relative to token count; AI favors a wide but consistent vocabulary, human writing repeats common words more naturally; (3) punctuation density — ratio of punctuation characters to total characters; AI tends toward clean, sparse punctuation while humans use dashes, ellipses, and parentheticals more freely; (4) average word length — a proxy for register; AI writing skews toward slightly longer, more formal words. These properties diverge because language models are trained to maximize fluency and coherence, which produces statistically regular output. What it *can't* capture: semantic meaning, intentional stylistic choices, or evidence of AI authorship in short texts where the sample size is too small for the statistics to be reliable.

**What does each signal's output look like?**

- LLM classifier: returns a float `llm_score` in [0.0, 1.0] where 1.0 = high confidence AI, 0.0 = high confidence human. The Groq prompt instructs the model to return only a JSON object `{"score": float, "reasoning": str}` so the score is parsed deterministically rather than extracted from free text.
- Stylometric heuristics: each of the four sub-measures is normalized to [0.0, 1.0] (higher = more AI-like), then averaged into a single `stylo_score` float in [0.0, 1.0].

**How will you combine them into a single confidence score?**

$\text{combined\_score} = 0.65 \times \text{llm\_score} + 0.35 \times \text{stylo\_score}$

The combined score is a weighted average of both metrics. The LLM carries more weight because it captures holistic patterns the surface heuristics miss.

Additionally, if the two signals diverge by more than 0.40, i.e.

$|\text{llm\_score} - \text{stylo\_score}| > 0.40$

the result is forced to "uncertain" regardless of the weighted average — disagreement between signals is itself evidence of ambiguity.

## Uncertainty representation

**Threshold summary table**

| `combined_score` range | `signal_divergence` | `attribution` |
|---|---|---|
| ≥ 0.75 | false | `"ai"` |
| ≤ 0.25 | false | `"human"` |
| 0.25–0.75 | any | `"uncertain"` |
| any | true (gap > 0.40) | `"uncertain"` (override) |

A `combined_score = 0.6` means the signals lean slightly toward AI but are not strong enough to cross the 0.75 threshold for a definitive label. The score sits in the uncertain zone (0.25–0.75), so the system returns `attribution: "uncertain"` with `confidence: 0.60`. It does *not* mean "60% chance it's AI" — it means "the weighted signal average is 0.60, which is below the confidence bar required to make a claim." A 0.6 is often caused by the LLM scoring moderate (e.g. 0.68) while the stylometric score is lower (e.g. 0.46), both landing in ambiguous territory.

**Threshold logic and `confidence` calculation**

The confidence scorer runs this logic in order:

```python
def confidence_and_label(llm_score: float, stylo_score: float) -> dict:
    combined_score = round(0.65 * llm_score + 0.35 * stylo_score, 4)
    signal_divergence = abs(llm_score - stylo_score) > 0.40

    if signal_divergence or (0.25 < combined_score < 0.75):
        label = "uncertain"
        confidence = combined_score
    elif combined_score >= 0.75:
        label = "ai"
        confidence = combined_score
    else:  # combined_score <= 0.25
        label = "human"
        confidence = (1 - combined_score)

    return {
        "attribution": label,
        "confidence": confidence,
        "combined_score": combined_score,
        "signal_divergence": signal_divergence,
    }
```

`confidence` means different things depending on the attribution:
- For `"ai"`: percentage confidence that the text is AI-generated (e.g. `combined_score = 0.82` → `confidence = 0.82`)
- For `"human"`: percentage confidence that the text is human-written, inverted from the AI-leaning scale (e.g. `combined_score = 0.10` → `confidence = 0.90`)
- For `"uncertain"`: the raw combined score — it is shown to the user as context, not as a directional confidence claim

## Transparency label design

A JSON object is returned in every `/submit` response under the key `"verdict"`. It contains three fields: `attribution` (string enum, same as label), `confidence` (float), and `message` (string). The `message` field uses the templates below — curly-brace tokens are interpolated at runtime.

**high-confidence AI** — `attribution: "ai"`

```
Attribution: Likely AI-generated ({confidence} confidence)

This text shows patterns consistent with AI authorship: the LLM classifier
scored it {llm_score} and the stylometric analysis scored it {stylo_score}
(higher = more AI-like on both).

Note: short texts and professionally edited writing can produce false positives.

Content ID: {content_id}
To dispute this result, POST /appeal with your content_id and a reason.
```

**high-confidence human** — `attribution: "human"`

```
Attribution: Likely human-written ({confidence} confidence)

This text shows patterns consistent with human authorship: the LLM classifier
scored it {llm_score} and the stylometric analysis scored it {stylo_score}.

Note: AI text explicitly prompted to sound informal or conversational can
produce false negatives.

Content ID: {content_id}
To dispute this result, POST /appeal with your content_id and a reason.
```

**uncertain** — `attribution: "uncertain"`

```
Attribution: Uncertain ({confidence} confidence)

The two detection signals returned conflicting results (LLM: {llm_score},
stylometric: {stylo_score}). This may mean the text mixes human and AI
writing, or that it falls outside the system's reliable detection range
(e.g. very short text, non-native English).

This result does not make a claim about authorship.

Content ID: {content_id}
To request human review, POST /appeal with your content_id and a reason.
```

## Appeals workflow

**Who can submit an appeal?**

Any caller who holds a valid `content_id` (returned in the original `/submit` response). No account or login is required — possession of the ID is the credential. The system rejects appeals for IDs that don't exist or are already `"reviewed"`.

**What information do they provide?**

`content_id`, provided when the user submit the text, and `reason`, a plain-text explanation in the submitter's own words (e.g. "I wrote this myself and it was flagged as AI").

**What does the system do when an appeal is received?**

If the provided `content_id` exists and has not been appealed, the system appends a log with the updated status and reason, then sends the user a confirmation of appeal.

**What would a human reviewer see when they open the appeal queue?**

Each queue entry surfaces:

- **Content ID**
- **Original text** (full, read-only)
- **Signal breakdown:** `llm_score`, `stylo_score`, `combined_score`, LLM reasoning string
- **Original verdict** and confidence %
- **Submitter's reason**
- **Timestamps:** submitted at, appealed at

## Anticipated edge cases

**Edge case 1: Very short text (under ~60 words)**

- *Example input:* a one-paragraph product review, a Slack message, a tweet
- *What happens:* TTR is artificially inflated in small samples (nearly every word is unique by default), and sentence length variance is computed over 1–2 sentences, making it statistically meaningless. `stylo_score` will be unreliable — likely drifting toward 0.45–0.55 regardless of authorship. The LLM also has too little context to assess coherence, and often returns a moderate score around 0.45.
- *Likely result:* `combined_score ≈ 0.47`, `attribution: "uncertain"` — technically correct but meaningless. Nearly all short texts land here, making the system useless for a common real-world input length.
- *How the code should handle it:* Before running the stylometric module, check `word_count = len(text.split())`. If `word_count < 60`, skip stylometric analysis, set `stylo_score = None`, and compute `combined_score = llm_score` directly (weight 1.0 on LLM only). Append a warning to the label message: `"Note: text is too short for stylometric analysis ({word_count} words). Result is based on LLM classification only."` The threshold logic and `confidence` calculation remain unchanged.

**Edge case 2: Formal academic or technical prose written by a human**

- *Example input:* a paragraph from a computer science paper, a legal clause, a medical chart note
- *What happens:* Formal writing deliberately minimizes stylistic variation — sentence lengths are consistent for clarity, vocabulary is domain-specific and repetitive (lowering TTR), punctuation is sparse (no em-dashes or ellipses), and word length skews long (technical terms). All four stylometric sub-measures score AI-like, pushing `stylo_score` to ~0.78. The LLM classifier partially compensates because it recognizes domain-specific conventions, scoring ~0.52.
- *Likely result:* `combined_score = 0.65 * 0.52 + 0.35 * 0.78 = 0.61`, `signal_divergence = |0.52 - 0.78| = 0.26` (below 0.40 threshold), `attribution: "uncertain"`. The underlying cause is a stylometric false positive, not genuine ambiguity — but the system has no way to distinguish these.
- *How the code should handle it:* Nothing in v1 can prevent this. It is a documented limitation. The "uncertain" label message already references "formally written text" as a possible cause; the appeals workflow is the correct resolution path. Do not add special-case logic for domain detection.

**Edge case 3: AI text generated with an explicitly informal voice**

- *Example input:* AI output from a prompt like "write this like you're texting a friend, use contractions and slang, be casual"
- *What happens:* Informal AI text uses short sentences, varied punctuation (ellipses, exclamation marks, fragments), and common low-complexity words — the opposite of what the stylometric signal is trained to flag. `stylo_score` drops to ~0.28 (looks human). The LLM classifier still detects elevated coherence and on-topic consistency, scoring ~0.58, but not enough to carry the combined score past 0.75.
- *Likely result:* `combined_score = 0.65 * 0.58 + 0.35 * 0.28 = 0.475`, `signal_divergence = |0.58 - 0.28| = 0.30` (below 0.40 threshold), `attribution: "uncertain"`. This is a false negative — the text is AI-generated but the system does not label it as such.
- *How the code should handle it:* The LLM signal weight of 0.65 exists partly for this reason — it partially resists stylometric spoofing. In v1, no additional mitigation is applied. If the LLM score alone is ≥ 0.75 but `stylo_score` is pulling `combined_score` below the threshold, the divergence rule (`|llm - stylo| > 0.40`) may eventually catch wider gaps — but a 0.30 gap does not trigger it. This is an acceptable v1 limitation, not a bug to fix.

## Architecture

2–3 sentence narrative describing the submission and appeal flows

write the path a single piece of text takes from submission to the label a user sees. Name every system component it touches and what each one does

Label each arrow with what passes between components (raw text, signal score, combined score, label text).

### submission flow

```
POST /submit
    │
    │ {text}
    │
    ├───────────────┐
    ↓               ↓
LLM signal      stylometric signal
    ├───────────────┘
    │
    │ {llm_score, stylo_score}
    │
    ↓
confidence scoring
    │
    │ {confidence}
    │
    ↓
transparency label
    │
    │ {attribution}
    │
    ├───────────────┐
    ↓               ↓
API response    audit log
```

The text will first go through the tools to calculate both signals, then a confidence scoring will be calculated and attribute labeled. A log of all the related information will be appended, and an API response is sent to the user.

**`/submit` API request body**

| key | type |
|---|---|
| `text` | str |
| `creator_id` | str |

**log JSON**

| field | type | source |
|---|---|---|
| `content_id` | str (UUID) | generated at request time |
| `creator_id` | str | supplied by the user |
| `timestamp` | str (ISO 8601) | generated at request time |
| `text` | str | supplied by the user |
| `attribution` | str enum | one of the labels `confident-human \| confident-ai \| uncertain` |
| `confidence` | float, 2 decimal places | $\text{combined\_score}$ or $1 - \text{combined\_score}$ depending on label |
| `llm_score` | float, 2 decimal places | LLM signal module output |
| `stylo_score` | float, 2 decimal places | stylometric module output |
| `status` | str | "labeled" |

**API response JSON**

| field | type | source |
|---|---|---|
| `content_id` | str (UUID) | generated at request time |
| `timestamp` | str (ISO 8601) | generated at request time |
| `attribution` | str enum | one of the labels `confident-human \| confident-ai \| uncertain` |
| `text` | str | supplied by the user |

### appeal flow

`POST /appeal → status update → audit log → response`

```
POST /appeal
    │
    │ {content_id, reason}
    │
    ↓
verify content_id
    │
    │ {message}
    │
    ├───────────────┐
    ↓               ↓
API response    audit log
```

The system will first validate `content_id` exists and current status is `"labeled"`, if so, append a log with `status: "under_review"`. An API response is sent to the user.

**`/appeal` API request body**

| key | type |
|---|---|
| `content_id` | str |
| `reason` | str |

**log JSON**

| field | type | source |
|---|---|---|
| `content_id` | str (UUID) | generated at request time, stored in audit log |
| `timestamp` | str (ISO 8601) | generated at appeal time |
| `reason` | str | supplied by user |
| `confidence` | float, 2 decimal places | $\text{combined\_score}$ or $1 - \text{combined\_score}$ depending on label |
| `llm_score` | float, 2 decimal places | LLM signal module output |
| `stylo_score` | float, 2 decimal places | stylometric module output |
| `attribution` | str enum | one of the labels `confident-human \| confident-ai \| uncertain` |
| `status` | str | "under_review" |

**API response JSON**

| field | type | source |
|---|---|---|
| `content_id` | str (UUID) | generated at request time, stored in audit log |
| `timestamp` | str (ISO 8601) | generated at appeal time |
| `reason` | str | supplied by user |
| `message` | str | "Your appeal has been received. A human reviewer will assess it shortly." or "content_id not found" |

### audit log

A simple logger provided by Flask in `jsonl`. The log is read-only by the user and can only be updated by the system when a user submit a text through `/text` or an appeal through `/appeal`.

## AI Tool Plan

### M3 (submission endpoint + first signal)

I will provide Claude Code with the "Detection signals" and "Architecture" sections to implement the submission endpoint, first signal, and logging, and write a stub for the second signal for testing. I will ask it to generate a Flask app where I can test the first signal works without implementing the second signal yet, then test the first signal with the app with some sample texts.

### M4 (second signal + confidence scoring)

I will provide Claude Code with the "Detection signals" and "Architecture" sections to remove the stub for the second signal and implement it so it integrates smoothly with the Flask app. Then, I will provide the "Uncertainty representation" section so Claude Code can generate the code to combine 2 signals into an uncertainty score. I'll check if scores vary meaningfully between clearly AI and clearly human text, and ask Claude using the "Anticipated edge cases" section if the generated results are expected or not.

### M5 (production layer)

Which spec sections you'll provide (label variants + appeals workflow + diagram)

I will provide Claude Code with the "Transparency label design" section to correctly implement the output label and message the user will see. Then, I will provide the "Appeals workflow" for Claude Code to implement tools for appealing. I will verify everything works by submitting sample texts and testing all three label variants are reachable and that an appeal updates status correctly.