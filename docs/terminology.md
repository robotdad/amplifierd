# Terminology Mapping: Technical to User-Facing

This document maps amplifierd's internal technical terminology to user-friendly
alternatives for product surfaces. It exists because the people building on
amplifierd (developers) and the people using those products (info workers) speak
different languages.

The target end user is someone like "Charlie" -- she uses the system daily, talks
to AI naturally, built her own orchestrator without knowing the term, and sends
PRs without knowing git terminology. She is technically curious but not a
developer. Product surfaces need to meet her where she is.

## Mapping Table

| Technical Term | User-Facing Alternative | When to Use Technical | Notes |
|---|---|---|---|
| daemon / service (`amplifierd`) | Amplifier service | API docs, developer guides, systemd/launchd config | In error messages, bridge both: "The Amplifier service (amplifierd) encountered..." |
| session | conversation | API references, SDK docs | A session is the server-side container; a conversation is how users think about it. |
| bundle | configuration / config pack | Plugin development docs, bundle authoring guides | Users think in terms of "my setup" or "my configuration," not bundles. |
| module | capability | Module development docs, entry point registration | "Capabilities" communicates what the system *can do* rather than how it's organized. |
| hook | automation / auto-action | Hook authoring docs, lifecycle documentation | Users understand "when X happens, do Y" -- frame it that way. |
| provider | AI model / model | Provider configuration docs, adapter implementation | Users care about which model they're talking to, not the abstraction layer. |
| orchestrator | engine | Orchestrator internals, control flow docs | Charlie built one without knowing the term. Users think "the thing that runs my steps." |
| tool | action | Tool implementation guides, MCP/protocol docs | "Actions" maps to what users see: things the AI can do on their behalf. |
| context | memory / background | Context management internals, token budget docs | Users think "what does the AI remember?" not "what's in the context window?" |
| event | update / notification | Event system internals, SSE protocol docs | Users see updates appearing; they don't think in terms of event streams. |
| SSE (Server-Sent Events) | live updates | Protocol implementation, streaming docs | Never surface "SSE" in a UI. Users see things updating in real time -- that's it. |
| working directory | project folder | Path resolution internals, filesystem docs | Matches how non-developers think about where their files live. |

## Principles

These rules were agreed on by the team to keep terminology consistent across
surfaces without sacrificing precision where it matters.

1. **Use technical terms in developer-facing contexts.** This includes developer
   documentation, API references, SDK guides, and AI agent context. AI agents
   need the correct technical terms to build correctly -- do not simplify terms
   in system prompts or tool descriptions.

2. **Use user-facing terms in product surfaces.** This includes UIs, onboarding
   flows, help text, tooltips, support conversations, and any surface where the
   audience is an end user rather than a developer.

3. **Maintain 1:1 mappings between terms and concepts.** Every technical term
   maps to exactly one user-facing term, and vice versa. Do not introduce
   synonyms that could create confusion (e.g., don't use both "channel" and
   "thread" to mean "conversation" in different parts of the UI).

4. **Bridge terminology when technical detail surfaces.** Error messages,
   debugging output, and diagnostic screens are places where technical terms
   necessarily appear. In these cases, lead with the user-facing term and
   parenthetically include the technical one: "The Amplifier service (amplifierd)
   encountered an error" or "Your conversation (session abc123) could not be
   resumed." This teaches without alienating.
