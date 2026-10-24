---
type: <type from commonmind.yaml>              # required
title: "<Title>"                                # required
description: "<One sentence: what this page is about.>"   # required
owner: <human:id | role:id>                     # required
data_class: <data class from commonmind.yaml>   # should (section 11)
tags: []                                        # optional
sources:                                        # should (section 5.4)
  - id: <key>
    resource: <sources/inbox/file.md | https://…>
    title: "<Source title>"
generated: {by: "<agent>/<version>", at: "<YYYY-MM-DDThh:mm:ssZ>"}   # should, written by the agent; or agent:<name> (section 5.2)
---

# <Title>

<Content. One changing fact lives on one page; link to it from elsewhere.>
<Cite key statements with footnotes, e.g. "Started in March 2026.[^<key>]"; <key> is an `id`
in `sources`. Link this page from at least one related page (index.md does not count).>

[^<key>]: <Source title>
