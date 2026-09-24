# Cannabis

**Canary Deployment & A/B Testing Harness for Prompts and Models**

One of the two project options for Group 14 in the ML System Design & LLMOps course (Scaler School of Technology).

## The problem

Changing a prompt or swapping a model in a production LLM system is risky: a change that looks better in offline tests can behave worse for real users. Teams need a safe way to ship changes gradually and prove they are actually better before rolling them out to everyone.

## What this project is about

A harness that lets you:

- Roll out a new prompt or model version to a small slice of traffic first (a canary), while everyone else stays on the current version.
- Run A/B tests that split traffic between two or more variants (prompts and/or models) so they can be compared side by side.
- Measure and compare how each variant performs, so the decision to promote, keep testing, or roll back is based on evidence rather than gut feel.
