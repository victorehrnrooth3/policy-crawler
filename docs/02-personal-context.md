# Personal Context (Preference-Profile Source Material)

This file is the source of truth for what the ranker is trying to align with. Step 5 (preference profile & ranker) bootstraps `profile.yaml` from this file. Update this file when my situation evolves; the next weekly self-update will surface a diff to bring `profile.yaml` in line.

Authoritative external profile: <https://victorehrnrooth.com>.

## CV summary

- **Education**
  - **Oxford MPhil in Economics** — Distinction. Strong micro/applied micro foundation. Top mark in Industrial Organization (92, exceptional at MPhil scale). Core Micro 86 with the cohort administrative-error caveat (every student could opt for a 60 floor; my actual mark was 86). Thesis with Distinction; advisor relationship is positive but the advisor is a less-published member of faculty — letters require active framing.
  - **University of Pennsylvania, BA in Mathematical Economics** — Summa Cum Laude with Distinction. A or A+ in all but one course (one A−), including Linear Algebra and Real Analysis (Adv Calc 360/361, A+ in both). Graduate-level coursework: ECON 681 (Microeconomic Theory), ECON 682 (Game Theory), STAT 776 (Applied Probability). Strong relationships with several professors who wrote my Oxford recs; one is a renowned-but-unconventional Wharton professor (heavy in startups + teaching, lighter on recent publications).
- **Work**
  - **McKinsey & Company** — currently <1 year tenure. On a project inside the **McKinsey Global Institute (MGI)** — McKinsey's internal policy think tank. Loving it. Also engagement experience adjacent to energy and corporate strategy.
  - **Constraint:** as a junior, I cannot fully solve for MGI-only work; it doesn't count for evaluations and isn't permanently bookable until manager. Rotations are limited.
- **Other signals**
  - **Finnish military leadership** — *sodanjohtaja* (battle leader / company commander) of 150. Genuinely unusual signal in the policy / civilian-research space, especially relevant to defense and national-security work.
  - **Languages** — fluent English, Finnish; French (good), some Swedish.
  - **Citizenship** — Finnish (EU). Right to work in EU + UK (subject to visa for UK as appropriate). US work auth status: requires sponsorship. This matters for filtering: roles that explicitly state "no sponsorship" are dealbreakers for US locations until we have clarity.

## Career thesis

I want to **re-launch toward ambitious, quantitatively serious policy work** on topics I care about: **energy, defense, geopolitics broadly, and tech / AI policy**. I love what MGI feels like — McKinsey-pace, intellectually serious, policy-flavored. I'm allergic to slow-bureaucratic-only roles, pure finance, and "business management" as a discipline.

The realistic forks are:

1. **Top US PhD** (econ-or-policy with real math) → academic-quality methods → OECD / IEA / Fed / top think tank / faculty-policy hybrid.
2. **Geopolitical-risk firm or asset-manager policy institute** (Eurasia Group, Rhodium, Macro Advisory Partners, BlackRock Investment Institute, KKR Global Institute) → consulting-pace policy/macro work, often a stepping stone to government / IGO / fund.
3. **Frontier-tech / defense / energy corporate policy** (Anthropic, OpenAI, Anduril, Palantir, NextEra, Form Energy, Commonwealth Fusion) → operational policy work close to leverage.
4. **Think tank or predoc** (RFF, Brookings, CGEP, CSET, Belfer, IISS, RUSI, Tony Blair Institute, Bruegel, IFRI, SIPRI) → research-credential-building, sometimes pre-PhD.
5. **IGO / YPP** (OECD YPP, World Bank YPP, IMF Economist Program, EU EPSO, IEA, NATO) → multilateral career path.

The ranker should treat all five forks as positive territory and not silently penalize forks 2/3 in favor of fork 1 just because they look less "academic."

## Topic interests (positive signals)

Heavy weight:
- **Energy economics & energy transition** — power markets, decarbonization, electricity systems, climate policy, energy security.
- **Defense & national security** — defense industrial base, NATO/European defense, defense technology, deterrence, autonomous systems policy.
- **Geopolitics & geo-economics** — US/China, sanctions, supply chain risk, critical minerals, trade policy, conflict / risk analysis.
- **Tech & AI policy** — AI safety, AI governance, semiconductor policy, frontier model regulation, dual-use tech.

Medium weight:
- Industrial organization (especially energy, telecom, defense IO).
- Macroeconomics with policy bite (inflation, fiscal, central banking).
- Climate & resource economics.
- Innovation policy.

Lower weight (interesting if intersecting heavy/medium):
- Development economics with infrastructure / energy / trade focus.
- European integration / EU governance.

## Topic interests (negative signals)

- Pure finance / IB / asset-management investment roles (without a research/policy lens).
- Traditional management consulting outside policy/energy/defense practices.
- Marketing / business management / OB academic tracks.
- Pure macro forecasting for trading desks.
- Roles where the deliverable is a deck for sales enablement.
- "Public affairs" jobs that are really lobbying / comms in disguise.

## Geography (rolling 18-month window)

| Window | Cities I'm willing to take roles in | Notes |
|---|---|---|
| Now (London-based) | London (primary); Brussels, Geneva, Paris (acceptable European policy hubs) | Wife is moving to London. |
| ~12 months out | Bay Area, Boston, NYC, Chicago, DC | Wife's likely US destinations. Bay Area > Boston ≈ NYC > DC > Chicago, biased by topic match. |
| Always acceptable | Helsinki (Finland — family ties); remote / hybrid global if topic match is strong. |
| Hard nos | Roles requiring relocation outside the above set without a strong topic-match override. |

The ranker's geography logic should soft-penalize misses, not hard-filter, and should weight London + the four US cities equally during the transition year.

## Posting types of interest (with context)

- **`role`** — full-time positions; primary case.
- **`fellowship`** — Knight-Hennessy (Stanford), Schwarzman (Tsinghua), Marshall, Rhodes, Mason (Harvard PPOL), TBI Future of Britain, Belfer fellowships. Treat as high-value if the host program / topic matches.
- **`predoc`** — RFF Predoctoral Fellow, Brookings RA, Federal Reserve Board / regional Feds RA, CSET Research Analyst, Becker Friedman Institute pre-doc, MIT Sloan / NBER predocs. Important even though I previously preferred not to take pay cuts — the calculus has shifted and the ranker should surface them.
- **`program_call`** — PhD program admissions windows for: Harvard PPOL Economics Track, Stanford GSB Political Economics, Stanford GSB Economic Analysis & Policy, Wharton Applied Econ, Columbia SIPA Sustainable Development, MIT IDSS SES, Princeton SPIA STEP, Berkeley ARE, Northwestern Kellogg MECS (with Northwestern Econ opt-in), Stanford E-IPER, Yale School of the Environment ENRE, UPenn Econ, Yale Econ. (Chicago Harris is paused for 2026-27 entry; Harvard PEG is closed and folded into PPOL Economics.)
- **`internal_rotation`** — MGI rotations and similar internal moves; surfaced when manually added as a source.

## Initial preference signals (seed for `profile.yaml`)

These are not exhaustive — they are the seed the ranker starts with. The weekly self-update will refine.

**Must-haves**
- Topic match to at least one of: energy, defense, geopolitics, tech/AI policy.
- Quantitative/analytical character to the role (policy research, modelling, data work, or rigorous strategy — not pure comms / pure ops).
- Compatible geography (see table above).
- Realistic seniority for a profile with Oxford MPhil + ~1–2 years McKinsey at the time of application.

**Strong positives**
- Mentions of: "energy transition," "decarbonization," "electricity markets," "climate policy," "AI safety," "AI governance," "frontier AI," "national security," "defense industrial base," "geopolitical risk," "geoeconomics," "industrial policy," "supply chain," "critical minerals," "semiconductor policy."
- Employer with research credibility in policy circles.
- McKinsey-pace expectations (fast, smart, deliverable-driven).
- International / multilateral exposure.
- Explicit pre-PhD value (RA / predoc / fellowship that feeds into top PhD programs).

**Strong negatives (dealbreakers)**
- "No visa sponsorship offered" for US-based roles (until status changes).
- Pure IB / sell-side / pure investment roles (LP / GP / trading desk).
- Marketing / sales / pure ops / pure comms.
- Lobbying-without-research.
- Locations outside the geography table without a high-priority topic match.

**Soft negatives (penalize, don't reject)**
- Slow-bureaucratic-only environments (some IGOs, some legacy think tanks).
- Roles requiring 5+ years of relevant experience (still surface; maybe interesting later).
- Topic adjacent but not core (e.g., development without infra/energy/trade angle).

## Exemplar liked roles (few-shot for the ranker)

The ranker prompt includes a small set of these as positive few-shot examples. Names + descriptions to keep them durable; URLs may rot.

- **Eurasia Group, Geo-technology Practice, Analyst** — NYC/DC/SF/London. Geopolitics × tech, McKinsey-pace, accepts 1–3 years experience explicitly.
- **Rhodium Group, Research Associate, China / Energy / Climate** — NYC or SF. Quantitative, rigorous, policy-leaning.
- **BlackRock Investment Institute, Macro/Geopolitical Researcher** — NYC / London / SF. Elite small team, policy-flavored macro research.
- **KKR Global Institute, Associate** — NYC. Geopolitics + defense industrial base lens, ex-CIA / military senior staff, hires at junior level.
- **Resources for the Future (RFF), Predoctoral Fellow** — DC. Most rigorous energy/environment policy shop in the US; explicit PhD pipeline.
- **Center on Global Energy Policy at Columbia (CGEP), Research Associate** — NYC. Bipartisan, technically deep, run by ex-officials.
- **Belfer Center Environment & Natural Resources / International Security, Research Fellow / Associate** — Boston. Combines two of my four interests.
- **CSET (Center for Security and Emerging Technology), Research Analyst** — DC. Premier AI-and-national-security shop, hires from consulting + government.
- **Tony Blair Institute (TBI), Tech & Public Services / Geopolitics** — London (HQ) and globally. Tech-policy positioning, pace, the Sanna Marin connection is a useful Finnish hook.
- **IISS (International Institute for Strategic Studies), Research Fellow** — London. Defense-focused, my Finnish military leadership lands here.
- **Anthropic Policy team / OpenAI Policy team, Policy Analyst** — SF / DC / London. Frontier AI policy.
- **Anduril Strategy / Palantir Strategy & Communications** — Defense-tech corporate policy/strategy.
- **OECD, Young Professionals Programme / IEA Energy Analyst** — Paris. Multilateral energy + economic policy.
- **Harvard PPOL Economics Track / Stanford GSB Political Economics / Wharton Applied Economics — PhD program calls** — fall application windows.

## Exemplar disliked roles (few-shot negatives)

- Goldman Sachs Investment Banking Analyst — NYC. Pure IB, no policy/research lens.
- BCG generalist consultant — London. Generalist consulting outside policy/energy/defense.
- LinkedIn Strategy & Operations Associate — Bay Area. Generalist tech ops without policy bite.
- Marketing Associate at a CPG brand — DC. Wrong discipline entirely.
- "Public Affairs Manager" lobbying-only role at a trade association — DC. Lobbying-without-research.
- A US-based startup PM role explicitly stating "no visa sponsorship."

## Trusted sources to monitor (high-priority think tanks)

This is my hand-curated, globally-distributed think-tank shortlist. Step 03 turns each of these into a row in `data/sources.yaml` (then into the `sources` table) at `priority = 5` for the most relevant to my topics, `priority = 4` for the rest. Source: `Top think tanks.xlsx` checked into the repo plus my own additions.

| # | Name | Country | Primary Research Focus | Languages | Notes |
|---|---|---|---|---|---|
| 1 | Brookings Institution | USA | Domestic & Economic Policy | English | |
| 2 | Carnegie Endowment for International Peace | USA | Foreign Policy & Peace | English | Brussels office. |
| 3 | Bruegel | Belgium | International Economics | English | |
| 4 | Center for Strategic and International Studies (CSIS) | USA | Defense & Global Security | English | |
| 5 | Chatham House | UK | International Affairs | English | |
| 6 | Council on Foreign Relations (CFR) | USA | International Relations | English | |
| 7 | Centre for International Governance Innovation (CIGI) | Canada | Global Economy & Technology | English | Has a digital-policy fellowship for students at Canadian institutions. |
| 8 | Atlantic Council | USA | Transatlantic Relations | English | |
| 9 | Belfer Center for Science and International Affairs | USA | Science, Tech & Global Security | English | Harvard Kennedy School. |
| 10 | French Institute of International Relations (IFRI) | France | Geopolitics & Security | French / English | |
| 11 | Peterson Institute for International Economics (PIIE) | USA | Trade & Global Macroeconomics | English | |
| 12 | Center for American Progress (CAP) | USA | Liberal/Progressive Policy | English | |
| 13 | RAND Corporation | USA | Multi-sector Research & Analysis | English | Defense, energy, tech all relevant. |
| 14 | Kiel Institute for the World Economy (IfW) | Germany | Global Economic Relations | English / German | |
| 15 | International Institute for Strategic Studies (IISS) | UK | Military & Conflict | English | High priority — London + defense fit. |
| 16 | Woodrow Wilson International Center for Scholars | USA | Humanities & Global Issues | English | |
| 17 | Centre for European Policy Studies (CEPS) | Belgium | EU Affairs & Governance | English | |
| 18 | Clingendael | Netherlands | Diplomacy & Security | Dutch / English | |
| 19 | Stiftung Wissenschaft und Politik (SWP) | Germany | Foreign & Security Policy | German / English | |
| 20 | Centre for Economic Policy Research (CEPR) | UK | European Economic Research | English | |
| 21 | Center for Social and Economic Research (CASE) | Poland | Socio-economic Analysis | English / Polish | |
| 22 | Human Rights Watch | USA | International Human Rights | English | |
| 23 | Stockholm International Peace Research Institute (SIPRI) | Sweden | Arms Control & Disarmament | English | High priority — defense/Nordic fit. |
| 24 | Danish Institute for International Studies (DIIS) | Denmark | Global Studies & Development | Danish / English | |
| 25 | Barcelona Centre for International Affairs (CIDOB) | Spain | International Relations | Spanish / Catalan / English | |
| 26 | Institute for International Political Studies (ISPI) | Italy | Geopolitics & Global Trends | Italian / English | |
| 27 | German Development Institute (IDOS) | Germany | Sustainable Development | English / German | |
| 28 | LSE IDEAS | UK | Diplomacy & Strategy | English | London + relevant. |
| 29 | Norwegian Institute of International Affairs (NUPI) | Norway | Global Power Relations | English / Norwegian | |
| 30 | Overseas Development Institute (ODI) | UK | International Development | English | |
| 31 | Japan Institute of International Affairs (JIIA) | Japan | Asia-Pacific Foreign Policy | Japanese / English | |
| 32 | International Crisis Group (ICG) | Belgium | Conflict Prevention | English | |
| 33 | Australian Institute of International Affairs (AIIA) | Australia | International Affairs | English | |

Step 03 also seeds additional source categories (asset-manager policy institutes, geopolitical-risk firms, corporate policy at frontier-tech / defense / energy companies, IGOs / YPPs, predoc programs, PhD program calls). The combined list is the v1 monitoring set.

## Updating this file

When my situation changes (new city locked in, new topic stops sparking joy, US visa status updates), edit this file directly and commit. The next weekly preference-self-update run will detect the divergence between this file and `profile.yaml` and propose a diff for me to approve.
