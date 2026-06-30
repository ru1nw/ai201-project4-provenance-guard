# ai201-project4-provenance-guard

## specs

### Content Submission Endpoint

a `POST /submit` endpoint takes the text that will be labeled.

the endpoint takes strings `text` and `creator_id` in the request body, and
returns `attribution`, `confidence`, `label`, and a unique `content_id`.

`attribution` could be 1 of 3 values: "uncertain", "ai", or "human", signifying
the system's decision if the submitted text is AI-generated, human-written, or
unclear. `label` contains more information about the decision.

### Multi-Signal Detection Pipeline

the detection pipeline uses 2 signals to determine how the system classify the
text, both returns a float between 0 and 1. the combination of these 2 signals
allow the system to assign a score to texts based on both the writing and the
meaning. using multiple signals gives the combined score a more holistic view of
the text, rather than simply relying on a single source of truth.

1.  LLM-based classification: this is the semantic signal. an LLM model reads
    the text and gives the text a score between 0 and 1 that signifies the
    model's guess of the attribution depending on how the words are chosen,
    sentences formed, and meaning conveyed.
2.  Stylometric heuristics: this is the pattern signal. a statistic algorithm
    calculates 4 sub-measures: sentence length variance, vocabulary diversity,
    punctuation density, and average word length, and the calculated measures
    are combined into a single score. this signal captures the more subtle,
    under-the-hood writing styles that are present commonly in AI or human
    writings.

of course, these 2 signals are not perfect, and accuracy fluctuates based on how
texts are written or prompted to be generated. a future improvement that could
be done would be to train the model with labeled corpus to improve accuracy, or
shift between weights and models to account for different writing styles across
different genres.

### Confidence Scoring with Uncertainty

The final combined score is calculated using a weighted average:

`combined_score = round(0.75 * llm_score + 0.25 * stylo_score, 4)`

`llm_score` is usually the more accurate signal, compared to stylometric which
performs better on AI-generated texts than human-written ones, so the score
weighted more on `llm_score`. an extra condition is also applied when the 2
signals have a divergence of more than 0.6, which makes the decision
automatically "uncertain" to account for discrepancy in decisions across
signals.

`confidence` means different things depending on the attribution:
-   For `"ai"`: percentage confidence that the text is AI-generated (e.g.
    `combined_score = 0.82` → `confidence = 0.82`)
-   For `"human"`: percentage confidence that the text is human-written,
    inverted from the AI-leaning scale (e.g. `combined_score = 0.10` →
    `confidence = 0.90`)
-   For `"uncertain"`: the raw combined score — it is shown to the user as
    context, not as a directional confidence claim

a better approach would be to train the scoring based on labeled corpus to more
accurately reflect the decisions based on real data instead of manual
adjustments.

#### examples

AI generated

```
Artificial intelligence represents a transformative paradigm shift in modern
society. It is important to note that while the benefits of AI are numerous, it
is equally essential to consider the ethical implications. Furthermore,
stakeholders across various sectors must collaborate to ensure responsible
deployment.

{"combined_score": 0.8001, "llm_score": 0.8, "stylo_score": 0.8005}
```

human written

```
ok so i finally tried that new ramen place downtown and honestly? underwhelming.
the broth was fine but they put WAY too much sodium in it and i was thirsty for
like three hours after. my friend got the spicy version and said it was better.
probably wont go back unless someone drags me there

{"combined_score": 0.224, "llm_score": 0.1, "stylo_score": 0.5961}
```

### Transparency Label

| `combined_score` range | `signal_divergence` | `attribution` |
|---|---|---|
| ≥ 0.75 | false | `"ai"` |
| ≤ 0.25 | false | `"human"` |
| 0.25–0.75 | any | `"uncertain"` |
| any | true (gap > 0.40) | `"uncertain"` (override) |

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

### Appeals Workflow

Any caller who holds a valid `content_id` (returned in the original `/submit` 
response). No account or login is required — possession of the ID is the
credential. The system rejects appeals for IDs that don't exist or are already
appealed.

If the provided `content_id` exists and has not been appealed, the system
appends a log with the updated status and reason, then sends the user a
confirmation of appeal.

### Rate Limiting

Rate limiting is implemented using Flask-Limiter with
`10 per minute;100 per day` for `submit` and `appeal` endpoints.

### Audit Log

A simple logger writes each submit and appeal events into a `jsonl` file. The
log is read-only by the user through `/log` and is only updated by the system
when a user submit a text through `/submit` or an appeal through `/appeal`.

One thing to note is that the `jsonl` log file also acts as a state manager for
appeals. When a content is submit for appeal, the system checks to find if the
content exists or had been submitted for appeal by going through the logs. This
can be better implemented by storing the content and its state in a database.

## Known limitations

```
The relationship between monetary policy and asset price inflation has been
extensively studied in the literature. Central banks face a fundamental tension
between their mandate for price stability and the unintended consequences of
prolonged low interest rates on equity and real estate valuations.

{"combined_score": 0.3618, "llm_score": 0.2, "stylo_score": 0.8472}
```

Human-written texts that are more polished such as the one above is more likely
to be misclassified due to the high score in stylometric.

Stylometric is manually tuned to capture general characteristics of AI written
content that uses vocabulary variation, sentence length variation, etc., making
this type of content more prone to be misclassifed. In this case, LLM classified
it as human written, which lowered the combined score and classified this text
as "uncertain", but the LLM is not guaranteed to be consistent for other
examples.

Stylometric will perform better if different weights are used across different
types of content, which requires a large set of labeled samples and weight
fine-tuning to achieve.

## Spec reflection

The spec helped me decide the fields and possible values of API endpoints and
logs, which also helped keeping the naming consistent for fields and variables.

The spec originally planned to use 60 words as the cutoff for stylometric
scoring to run, so the result is not artificially inflated for shorter texts.
However, all given examples are under 60 words, so I implemented Claude's
suggestion to run 2 out of the 4 sub-measures that can still perform reliably on
shorter texts.


## AI usage

Claude Code originally wrote the log functions in `app.py`, but that was before 
I implemented the appeal workflow in `appeal.py`, which required log functions.
I ended up moving the log functions to a separate file `log.py` so both `app.py`
and `appeal.py` can use the functions.

Claude Code originally use stylometric scoring as the sole signal to assign
classifications if LLM failed to produce a score for some reason. However, due
to stylometric scoring being highly undependable, I changed it so the system
produces an error message to the user if LLM failed to avoid misclassification.