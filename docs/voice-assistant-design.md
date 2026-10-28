# Voice: "Hey Lara", satellites, and a voice with a memory

Status: design, 2026-10-28, rev 4 (rev 2: companion review GREEN; rev 3: aligned with what
Vornik actually does today; rev 4: no privacy between household members, see the change
notes at the end). Nothing here is built yet.

## Summary

One persona, **Lara**, answers on every satellite in the house: the southern English
voice, the "Hey Lara" wake word, the dry wit. Instant commands ("lights off") are decided by
Home Assistant locally, in well under a second, and never leave the house. Everything else
goes to an LLM agent with Lara's persona. When Vornik's Home Assistant integration ships,
that agent gains Vornik's tools: household memory, news briefings, email and calendar,
spoken back on the satellite that asked. Memory is what turns Lara from a light switch with
a voice into someone you can pick a conversation up with tomorrow.

This design is the house side. The Vornik side is Vornik's own design
(`docs/low-level-design/2026-10-24-home-assistant-agent-design.md` in vornik-enterprise:
"Vornik as tools behind Assist"), and this one is shaped to plug into it unchanged.

## 1. As-built (read from the instance, 2026-10-25)

| piece | today | consequence |
|---|---|---|
| pipeline | one, "Home Assistant", preferred | every satellite would get the same agent and tools |
| speech-to-text | Whisper app, model `auto` = `tiny-int8` on this ARM host | the weakest model: room names, "Lara", children's speech will suffer |
| conversation agent | Ollama integration titled "Vornik" (Vornik's OpenAI/Ollama-compatible endpoint), model `gemma-4-26b`, Lara persona prompt, tools: Assist API, 20 turns of history | works, but the text of every request leaves the house for a hosted model |
| `prefer_local_intents` | **off** | even "lights off" waits for the LLM |
| text-to-speech | Piper app, `en_GB-southern_english_female-low` | the voice; only a `low`-quality model exists for it |
| wake word | none configured; "Hey Lara" published as an openWakeWord ONNX model (`home-assistant-wakewords-collection`, `en/Hey Lara/lara.onnx`) | its card reports recall 0.52: it misses about half of the times it is called |
| satellites | none in Home Assistant yet | |
| local intents | the built-in agent answers only for exposed entities; "temperature in the kitchen" fails today (`no_valid_targets`) | exposure has to be curated before local intents are useful |

## 2. Goals and non-goals

Goals:

1. Wake on "Hey Lara" on every satellite, reliably, with children and a TV in the room.
2. Device control and simple questions answered locally, fast, in Lara's voice.
3. Conversation: follow-ups without the wake word; a topic that can be resumed later.
4. Sensitive capabilities (email, calendar, briefings) only where they belong, never in a
   children's room, never approved by voice.
5. The house speaks to people through Lara: announcements, briefings, reminders.

Non-goals: speaker identification (neither side has it, see §7); replacing the phone as
the place where approvals and private content land; anything that needs the Alexa cloud.

## 3. Architecture

```
 satellite: rooted Echo Show / Spot (VACA)  or  ESPHome satellite (Voice PE class)
   │ on-device wake word "Hey Lara" (microWakeWord)
   │ audio
   ▼
 HA Assist pipeline (one per permission tier, chosen per satellite)
   ├─ STT: Whisper app, model chosen by measurement (§9)
   ├─ local intents FIRST (prefer_local_intents: on) ──► device control, timers, states
   └─ no match ──► Lara agent (LLM) ── tools:
                      Assist API             (house control, every tier)
                      Vornik LLM API         (memory, briefing, mail, calendar: adult tier only)
   ▼
 TTS: Piper, southern English female ──► the satellite that asked

 the house speaking first:
   automations ───────────────────────► assist_satellite.announce / start_conversation
   Vornik push ──► vornik integration ─┘ (area-targeted, quiet at night)
                   (its webhook; Vornik holds no Home Assistant token)
```

Vornik never calls Home Assistant directly: a finished task is pushed to the integration's
webhook, and the integration, which knows which satellite asked, does the announcing.

The LLM is reached through Vornik's model endpoint as today; Vornik's own integration, when
it ships, adds an **LLM API** ("Vornik") of tools beside the Assist API. Vornik is never put
in front of Assist (its design §2.0 withdrew that): what must be instant stays local.

## 4. The wake word: "Hey Lara" v2

The published model is an openWakeWord ONNX file with recall 0.52. Two problems: it misses
half the calls, and VACA expects to drop openWakeWord-ONNX support (its wiki: "OpenWakeWord
using Onnx will be removed in a future version"), keeping openWakeWord-TFLite and
microWakeWord.

Plan:

- **Train a microWakeWord model** (`hey_lara.tflite` + `.json`). One artefact serves both
  satellite families: VACA loads microWakeWord models from `config/vaca/custom/` and syncs
  them to every device, and ESPHome's `micro_wake_word` takes the same model by URL. It uses
  about a quarter of openWakeWord's CPU (VACA wiki), which matters on an Echo Show 5.
- Keep an **openWakeWord-TFLite** conversion as the fallback engine on VACA.
- **Training data:** synthetic positives from many Piper voices (the standard recipe), plus
  real recordings from the household, adults and children, with consent, near and far, TV
  on. Negatives: the household's own TV and conversation audio, which is what will cause
  false wakes. Children's voices are the population most likely to be missed.
- **Acceptance**, measured on held-out household recordings rather than the training
  report: recall at least 0.90 at no more than 0.5 false wakes per hour of TV audio. The
  model, its card and the measurement script are published in the wake-word collection fork.
- Until v2 passes, satellites run the existing ONNX model on openWakeWord with a lowered
  threshold, tuned with VACA's on-screen diagnostics.

## 5. Satellites

### 5.1 With a screen: rooted Echo Show and Echo Spot (LineageOS + VACA)

The screen devices run LineageOS (Echo Show 5/8 via the XDA work; the first-generation Echo
Spot via the EchoPortal fork) and the **View Assist Companion App**. VACA is a full Assist
satellite with its own wake-word engine, a dashboard browser, a media player and device
sensors, and each device picks its own pipeline. On these devices:

- wake word: microWakeWord "Hey Lara" (§4);
- the screen shows a View Assist or Lovelace view for the room, and the response text while
  Lara speaks;
- each device is assigned to its area, so "lights off" means this room's lights;
- the device's pipeline select is set by tier (§6).

### 5.2 Without a screen: the Echo Dot and Echo Plus

A Gen3 Echo Dot and a Gen1 Echo Plus remain on Alexa. No persistent local firmware is
published for either model: community projects cover the second-generation Dot (EchoLocal)
and the second-generation full-size Echo (LibreEcho, in progress), not these two.

| option | what | for | against |
|---|---|---|---|
| **A. Replace with an ESPHome satellite (Voice PE class)** | Home Assistant Voice PE or an ESP32-S3 box per room; retire the Echo or keep it for Alexa-only uses | on-device "Hey Lara" (same microWakeWord model), echo cancellation, local, supported | about €100 per room; the Echo's better speaker is lost unless a line-out speaker is added |
| B. Keep the Echo as a speaker for a Voice PE | the Voice PE listens; Lara's replies play on the Echo via `alexa_media` announcements | keeps the Echo's speaker | replies go through Amazon's cloud and lag; two devices per room; an Alexa outage silences Lara |
| C. Alexa skill bridge ("Alexa, ask Lara...") | a custom Alexa skill forwards text to Assist | no new hardware | two wake words, Amazon in the loop, no "Hey Lara" at all |
| D. Wait for a community port | watch EchoLocal / LibreEcho for these models | free, keeps the hardware | open-ended; nothing published today |

**Recommendation: A**, one room at a time, starting with the busiest room. B only where
the Echo's speaker is worth keeping and the lag is acceptable. D is free to watch in
parallel. This is the operator's decision; nothing else in this design depends on it.

## 6. Pipelines and permission tiers

Home Assistant assigns a pipeline per satellite (the satellite's "assistant" select), and
the tools an agent may call are set per conversation agent (`llm_hass_api`, a list, read
from the Ollama integration's agent options on this instance). Together those give
per-room permissions without any speaker identity:

| tier | satellites | agent | tools | prompt |
|---|---|---|---|---|
| **Lara** | living spaces, the adults' bedroom, the office | "Lara" | Assist API, Vornik API (when it ships) | full persona, sensitive capabilities allowed |
| **Lara, family** | children's rooms, guest room | "Lara (family)" | Assist API only | family-safe persona, no memory writes, no sensitive tools |

Both pipelines: Piper with Lara's voice, the same STT, `prefer_local_intents: on`. A
satellite with no pipeline selected falls back to the preferred one, so **the preferred
pipeline is the family tier**: a new or reset device starts with fewer powers, not more.

This answers the open question in Vornik's design review (F4): the partition is real
because a family-tier agent is never given the Vornik API, so its tools do not exist for
it. That is verified by test (§10), not assumed.

**What the tiers do not do, stated plainly:** they partition by ROOM, not by person. A child
in the living room talks to the full Lara, with memory and, later, mail and calendar. That
is the accepted limit of a house with no speaker identity. It is why §7 keeps private
content short and offers the phone instead, why nothing is ever approved by voice, and why
memory written by voice is only a proposal (§8).

**Whose mail, in which room.** No privacy between household members (operator,
2026-10-28: "we don't care about privacy in this family"). One adult's own mailbox and
calendar are spoken on any Lara-tier satellite, like the household-level results (the school
e-mail digest, the shared calendar). These workflows are therefore **not** marked `private`
in Vornik, and one Vornik integration entry with one key serves every Lara-tier satellite;
there is no per-adult entry. Vornik's `private` delivery rule stays available should that
ever change; it would be a configuration change, not a prompt instruction.

**Other entry points use the preferred pipeline too:** the Home dashboard's "Ask" quick
action and the phone app's Assist. With the family tier preferred, the dashboard button
names the Lara pipeline explicitly (its `assist` action takes a `pipeline_id`), and each
adult sets Lara as the default assistant in their own app. A test asserts the button names
it.

## 7. Persona and speech

The persona stays Lara: dry, sarcastic, ultimately on your side. What changes is what the
prompt adds for speech and for the household:

- **Spoken, not written:** one to three short sentences; no lists, markdown, emoji or
  URLs; numbers and units as they are said ("twenty-one degrees").
- **Who may be listening:** the voice cannot tell who is speaking. Children, guests and
  grandparents use the same satellites. The family-tier prompt keeps the attitude but
  drops anything a child should not hear, and never mentions the adults' mail, calendar or
  memories.
- **Honesty about the house:** say what was done and what failed, never claim an action the
  tool result does not show.
- **Short replies win:** a request that needs a long answer offers to send it to the phone.

## 8. Conversation and memory

Three horizons, each owned by a different layer:

| horizon | example | mechanism |
|---|---|---|
| a turn and its follow-ups | "Lights off." "And the hallway?" | Home Assistant's chat log for the `conversation_id` (20 turns today); **continued conversation**: when Lara ends on a question, the satellite listens again without the wake word |
| the house starting a conversation | "The washing is done. Shall I remind you in an hour?" | `assist_satellite.start_conversation` from an automation |
| across days | "Lara, where did we get to with the holiday plans?" | **Vornik memory** via its LLM API: `recall` in the turn, `remember` when asked ("remember that...") |

Rules for memory, matching Vornik's design:

- Memory is **household** memory. Nothing is filed under a person, because nothing knows who
  is speaking.
- Only the **Lara** tier can write. A family-tier satellite cannot, so a child cannot poison
  or read it from their room.
- What is remembered by voice lands as an unverified note, and Lara says so ("noted; it's
  marked unverified"). Vornik has **no step today where a person confirms such a note**: it
  stays labelled unverified, and recall shows the label. What does exist is listing and
  forgetting (Vornik's memory page, the phone export). A confirm step is a gap on the Vornik
  side, raised there; until it ships, Lara must not say "confirm it in Vornik".
- Lara does not silently log conversations into **memory**. Resuming a topic works because
  it was remembered on purpose, or because Vornik's briefings and tasks carry their own
  history. That is not the same as "not recorded": Vornik keeps an audit record of every
  LLM turn it serves (§11).

## 9. Speed and accuracy

Target, on this host (an RK3588-class ARM board, CPU only, which also runs Frigate and
the rest of Home Assistant): a local command answered within 1.5 s of the end of speech; an
LLM answer starting to speak within 3 s. Option B of §5.2 adds Amazon's round trip; if it
pushes a room past 3 s, that room moves to option A.

- **STT model by measurement, not by `auto`.** Record a set of household commands (both
  adults, a child, kitchen noise, TV on) and score `tiny-int8` (today), `small-int8`,
  `distil-small.en` and Parakeet (sherpa backend) for word error rate and latency on this
  host. Use Whisper's `initial_prompt` for the house vocabulary: Lara, the room names.
- **`prefer_local_intents: on`**: device control never waits for the LLM.
- **Exposure:** expose to Assist what people actually ask about. Curate by label, in the
  same way as the dashboards, rather than by hand-picked entity.
- **Streaming:** Home Assistant streams LLM text into Piper sentence by sentence; keep
  answers short so the first sentence arrives early. The model is reached through Vornik's
  endpoint, so Vornik is on this path and its share of the 3 s is measured, not assumed
  (§14).
- **Memory answers cost more.** A Vornik `recall` inside a turn took 0.5 to 2.2 s when Vornik
  measured it (2026-10-24), and the model then needs a second pass to answer. A memory answer
  will often miss 3 s. The target is for answers without a Vornik tool; memory answers get
  their own number, measured in P5.

## 10. Testing (write the test first)

`tests/voice/`, following the repo's rule:

1. **Intent cases:** sentences and the action Home Assistant must take, run through the
   built-in agent. Run in CI against the invented house of `tests/fixtures/synthetic.py`,
   where turning a light on harms no one (`conversation.process` executes what it matches,
   so these never run against the real house).
2. **Tier isolation:** the family-tier agent's tool list contains no Vornik tool; every
   satellite has a pipeline selected; the preferred pipeline is the family tier; the
   dashboard's "Ask" names the Lara pipeline. In P2, a satellite's selection is cleared by
   hand and it must answer as the family tier (the fallback in §14).
3. **STT benchmark:** the recorded set, scored per model (local only; the recordings are
   household voices and never leave the machine).
4. **Wake word:** recall and false wakes per hour on held-out household audio (local only).

Things no test can reach (audio quality, a real child's voice through a real Echo) are
verified by hand and written down as such.

## 11. Privacy

| data | where it goes |
|---|---|
| audio | the satellite and this host only (wake word on device, STT local) |
| a local-intent request | nowhere: decided on this host |
| an LLM request | its text goes to Vornik and, through Vornik, to a hosted model. Vornik keeps an audit record of each turn: the latest request, Lara's reply and the persona prompt, redacted, for 90 days by default (`retention.chat_audit_days`) |
| a Vornik tool call (P5) | Vornik records each call against the key that made it |
| memory | Vornik, until forgotten; spoken only on Lara-tier satellites |
| mail, calendar | read by Vornik; results spoken on any Lara-tier satellite, one adult's own included (no privacy between household members, §6); approvals on the phone only |
| recordings for training and benchmarks | local; the wake-word model is published, the recordings are not |

## 12. Phases

| phase | what | done when |
|---|---|---|
| P0 | `prefer_local_intents` on; STT benchmark and model choice; speech rules in the prompt; exposure curated | intent cases green; local commands answered locally |
| P1 | "Hey Lara" v2 (microWakeWord, plus OWW-TFLite fallback) | acceptance numbers in §4 met on household audio |
| P2 | screen satellites on VACA, areas set, two pipelines | tier-isolation tests green; each device answers for its own room |
| P3 | the Echo Dot / Echo Plus decision (§5.2) and its rollout | operator's choice made and built |
| P4 | announcements through Lara, quiet at night | morning briefing and reminders spoken in the right rooms |
| P5 | Vornik integration: memory, briefings, mail, calendar (Vornik's slices H0 to H9; its H0 spike and this design's §14 check the same Home Assistant facts, on one dev container) | resume-a-topic works on a Lara-tier satellite; family tier verified unable; a private result never spoken in a living space; memory-answer latency measured |

## 13. Decisions for the operator

1. The Echo Dot and Echo Plus (§5.2). Recommendation: A.
2. Which rooms are the family tier. Proposed: the children's rooms and the guest room.
3. Whether the family tier uses the same hosted model or a local one, so that children's
   requests never leave the house.
4. The family-tier persona: Lara with attitude but clean, or a gentler Lara.

## 14. Unverified (to confirm before building on them)

- VACA on the specific LineageOS builds in use: microWakeWord performance on the Echo Show 5
  and the Echo Spot (first generation).
- Continued conversation on VACA satellites (documented for Home Assistant's own satellites).
- That Home Assistant's pipeline fallback, for a satellite with none selected, is the
  preferred pipeline (§6 relies on it; tested in P2).
- Piper speaking-rate and noise settings that keep the `low` model intelligible at a
  distance.
- That Home Assistant's Ollama integration streams the reply into Piper sentence by sentence
  when the endpoint is Vornik's (Vornik's endpoint has a streaming path; the end-to-end
  behaviour is unmeasured), and how much of the 3 s Vornik's hop takes.

## Changes in rev 3 (2026-10-25)

Checked against Vornik's code and its design record:

- §8: Vornik has no confirm step for a voice-remembered note, so Lara no longer tells
  people to confirm it there; the gap is raised on the Vornik side.
- §8, §11: "not logged into memory" is kept, and the audit record Vornik keeps of every
  LLM turn is now stated, with its retention.
- §6, §11: one adult's own mail and calendar are spoken only on that adult's satellite or
  sent to their phone, matching Vornik's `private` delivery rule.
- §3: Vornik's pushes go to the integration's webhook; Vornik never holds a Home Assistant
  token.
- §9, §14: Vornik is on the LLM path, so its share of the latency is measured; memory
  answers get their own budget.

## Changes in rev 4 (2026-10-28)

- §6, §11: no privacy between household members, by the operator's decision. One adult's
  own mail and calendar are spoken on any Lara-tier satellite; those workflows are not
  marked `private` in Vornik, so a single Vornik integration entry serves all Lara-tier
  satellites. Rev 3's "only on that adult's satellite or phone" is withdrawn. Nothing
  else changes: family-tier rooms still get no Vornik tools, and nothing is approved by
  voice.
