# Case study: a QA helper for a bilingual phone team

**Demo scenario. Puentara is a fictional company.** All calls, agents and numbers in this case study are synthetic.

## 1. The situation

Puentara is a money app for freelancers and small businesses in the US and Latin America. Its support team takes calls in English and Spanish: lost cards, locked accounts, pending transfers, charge disputes, fee questions.

A small QA team reviews those calls. They check that each agent greets the customer properly, verifies identity before talking about the account, reads the recording notice, shows empathy, and gives clear next steps. Above all, they check that no agent ever asks a customer for a PIN, a full card number or a one-time code.

## 2. The problem

- **Reviewers only see a small sample.** Listening to a call and filling in a form takes time, so most calls are never reviewed.
- **Scores depend on the reviewer.** Two reviewers can score the same call differently, and the agent gets mixed feedback.
- **Risky moments slip through.** An agent who asks "what's your PIN?" on one unreviewed call can stay unnoticed until it leads to fraud or a complaint.
- **Spanish calls wait.** On a bilingual team, Spanish calls sit in the queue until the reviewer who speaks Spanish has time.

The cost is reviewer hours, agents coached on inconsistent feedback, and real risk to customers.

## 3. The solution, as the reviewer sees it

The reviewer runs one command on a folder of call transcripts and opens the review page it writes:

- Every call has a **suggested score** and a status for each rubric item: met, partial, not met, or not applicable.
- Every status shows **why**, with a link to the exact line and a short quote. The reviewer does not have to search the call to check it.
- Calls where an agent asked for sensitive data show a red **auto-fail flag** on the exact line, with the score held at 0 until the reviewer confirms it.
- A promise like "you'll definitely get your money back" on a dispute call is flagged for the reviewer to check.
- Each call ends with **"Reviewer decision: pending"**. The tool suggests. The reviewer decides.
- A per-agent table shows calls scored, average suggested score, flags, and the items each agent misses most, which gives coaching a starting point.
- The page, the summary and the explanations work in English or Spanish, so either reviewer can check a Spanish call. The quotes stay in the call's own language.

Card numbers and codes are masked before anything else happens, so they do not appear on the page, in the CSV, or in anything sent to the AI.

## 4. What was built

- A Python command-line tool (`score.py`) with three dependencies.
- An editable rubric file (`rubric.json`) with items, weights and phrase lists in both languages.
- Rule checks for sensitive-data requests, promised outcomes, the recording notice and the greeting. These need no AI.
- Claude (Anthropic's API) judges three softer items: identity verification, empathy and resolution. The code checks every quote it gives.
- A demo mode with hand-written AI answers, so it runs with no API key.
- A static HTML review page, a CSV export, and 202 automated tests.

## 5. What the demo shows (sample data)

The demo scores 6 synthetic Puentara calls, 3 in English and 3 in Spanish. These numbers come from running `python score.py` on that sample data. In demo mode, the AI answers are hand-written examples, not real model output. The rules and the scoring run for real.

- **1 auto-fail flag:** in call C002 (Spanish) the agent says "dime tu PIN de la tarjeta" on line 7. Suggested score 0, provisional until a reviewer confirms.
- **1 outcome-promise flag:** in call C003 (English, a charge dispute) the agent says "you'll definitely get your money back".
- **1 card number masked:** in call C006 a customer reads out their card number. It is hidden, and it does not count against the agent.
- **1 item sent to review:** one hand-written AI answer in C006 quotes words that are not in the call, on purpose. The tool catches it and leaves that item out of the score instead of trusting it.
- **Per-agent averages:** 92, 50 and 86 out of 100 across the three demo agents.

There is also an evaluation script that checks the rule layer on 40 labeled synthetic calls. It catches all 10 sensitive-data requests in that set and wrongly flags none of the 10 trap calls. Those calls come from the same templates the rules were built on, so the result is high by construction. It shows the rules work on that set. It is not real-world accuracy, and the README lists phrasings the rules still miss.

## 6. How this would work for a real team

- **Your rubric.** Replace the example rubric with your own QA form: your items, weights, required disclosures and approved greeting wording. The example is generic and not taken from any company's procedure.
- **Your transcripts.** The tool reads text transcripts, one file per call. Export them from your call-center or transcription tool and convert them to the simple `Agent:` / `Customer:` format. A direct import for your tool's export format can be added.
- **Your rules.** Add the phrases your agents really use, and the ways customers are told about recording and timelines, in both languages.
- **Your tone.** The explanations follow the instructions in one prompt file, which can be adjusted to your team's coaching style.
- **A trial first.** Run it on calls your reviewers have already scored, compare, and adjust before relying on it. Live AI judgment has not been tested on real calls yet, so this step matters.
- **Data handling.** Only masked transcript text goes to Anthropic, and only when live mode is on. Names and emails are not masked today. If your policy needs that, it is the first thing to add.

Want to see how it scores your calls? Send me two or three anonymized transcripts and your QA form, and I'll show you what the review page looks like with your rubric.
