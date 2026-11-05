# Demo video script (≈4 minutes)

Audience: Nils (founder) and Freddie (COO). The story: **X is where robotics news breaks. Scout watches it,
keeps only the signal, follows every post to its paper and code, and lets the team search all of it from
Discord.** Show, don't explain. Keep code on screen under 20 seconds in total.

## Before you hit record

- [ ] Run the bot on the demo database (`DATABASE_URL=…/scout_demo uv run scout bot`). Don't reset it: the search
      shots need the stored data.
- [ ] Clear the #feed channel first, so the scan is the first thing on screen.
- [ ] Have one X post link ready to paste: a robotics post that links a paper.
- [ ] Optional: Claude Desktop with the MCP snippet from the README, pointed at the same `DATABASE_URL`.

## Script

**0:00–0:20 · The problem** *(Discord, #feed empty)*
> "Robotics news breaks on X: a lab posts the demo, the paper and the repo. But X is also mostly noise. So I built
> Scout. It watches X, keeps the signal, and gives the team one place to search it."

**0:20–1:20 · Monitoring** *(type `/scan` in #feed)*
> "Every two hours Scout scans X two ways: about eighty trusted accounts across all of robotics, plus anyone who
> links to a paper or repo, or breaks big news. I can also just ask it to scan now."

*(the brief arrives as cards: poster, picture, likes, paper and code links)*
> "Free rules drop spam and posts nobody's engaging with. Claude reads what's left and throws out promo,
> off-topic and noise. What's left becomes the brief: the top stories, each led by the X post and linked to its
> paper and code. Every link comes from the database, so it can't invent one. It posts this every morning."

**1:20–1:45 · Team links** *(paste the X post in #links → ⏳ → ✅ → 4 bullets)*
> "Anyone can drop a link. It follows the post to the paper and tells us why it matters to Auki."

**1:45–3:00 · Search, two ways** *(Discord)*
- `/topic humanoids`:
  > "Simple search is a slash command. No AI, instant. Each post shows the paper or code it links to."
- `/author hut` → pick Marco Hutter from the autocomplete:
  > "By author: autocompletes from what's stored, and it's typo-tolerant."
- `@Scout what did ETH's legged robotics people post about navigation, and is there code?`
  > "And plain language. It's the same search: Claude just fills in the author, topic and date for me, then
  > answers with sources. Here it found the X post and the arXiv paper Scout followed it to."
- `/recent`:
  > "And this is how you see what's stored."

**3:00–3:30 · The radar learns** *(a `⭐ @someone…` suggestion, or type `/follow` live)*
> "When an account outside the radar keeps getting through, Scout suggests it. A human decides with /follow."

**3:30–4:00 · Why trust it** *(README: the funnel diagram, then the eval table)*
> "It covers robotics in general. Each item gets an importance score, and a separate flag for what matters to Auki. It's measured: precision 1.0 on real posts.
> It costs about twelve dollars a month of Claude plus X credits, and it all runs on one laptop.
> It's also an MCP server, so Claude Desktop or Cursor can query the same database."

## If something goes wrong on camera

- **The scan finds little:** `scout brief --hours 24 --post` posts a brief from what's stored.
- **A link reply takes >10s** (following the post to its paper): keep talking about what it's doing.
