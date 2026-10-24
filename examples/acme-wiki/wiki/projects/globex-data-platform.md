---
type: project
title: Globex – Data Platform
description: Building a shared data platform for Globex sales and finance, 2026.
owner: human:jdoe
data_class: confidential
project_status: active
tags: [data-platform]
sources:
  - id: kickoff
    resource: sources/inbox/2026-03-02-globex-kickoff.md
    title: Globex kick-off notes
    author: human:jdoe
    last_modified: "2026-03-02T16:00:00Z"
  - id: dmbok
    resource: https://www.dama.org/cpages/body-of-knowledge
    title: DAMA-DMBOK (external reference)
generated: {by: "agent:wiki-update", at: "2026-10-16T09:00:00Z"}
verified:
  - {by: "human:jdoe", at: "2026-10-16T10:30:00Z"}
stale_after: "2027-04-01T00:00:00Z"
---

# Globex – Data Platform

**Client:** [Globex](/organizations/globex.md)

## Goal

One shared data platform for sales and finance by the end of 2026.[^kickoff]

## Approach

Two-week sprints, each closed with a [retrospective](/methods/retrospective.md).[^kickoff]
Data governance follows DAMA-DMBOK.[^dmbok] The platform runs
[in the EU only](/decisions/globex-eu-region.md).

[^kickoff]: Globex kick-off notes
[^dmbok]: DAMA-DMBOK
