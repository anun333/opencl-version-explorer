# Publishing: what is live, and how to take it down

## What is published (2026-10-03)

- Repository: https://github.com/anun333/opencl-version-explorer (public; free Pages require that)
- Explorer: https://anun333.github.io/opencl-version-explorer/

**Voting was taken down on 2026-10-03.** The vote page, its data files and the 54 poll issues (14 directions, 40 concerns) were removed, and the explorer no longer links to them. The code is kept so it can be switched back on (below). Nothing had been voted on or replied to when it was removed.

**Appendix H wording is shown, with attribution.** The *Optional features* tab shows appendix H's tables and prose under CC BY 4.0, relying on the repository's `LICENSE` and README (the file itself has no licence header; 119 of 122 sibling files do). `CREDITS.md` has the reasoning and the list of changes made to the text. To withhold the wording again (names, counts and a link to the spec stay), build with `WITHHOLD_APPENDIX_H=1 python3 tools/build_viewer.py`, rebuild the site and push. A short licence question to the maintainers, asking them to confirm and add the missing headers, is optional; a draft is in the conversation history, not in this repository.

## Switching voting back on (not done; shown for completeness)

Voting is a GitHub-native design with no server: each direction and each concern is an issue in the repository, a vote is a 👍/👎 reaction on it, a reply is a comment, and `vote.html` reads counts and replies from the GitHub API in the visitor's browser. To re-enable:

1. `VOTING=1 python3 tools/build_model.py && python3 tools/build_viewer.py` (adds the vote links to the explorer)
2. `python3 tools/build_site.py --with-voting --repo OWNER/REPO` and change the workflow's build step to pass `--with-voting`
3. `python3 tools/seed_votes.py OWNER/REPO --site-url https://OWNER.github.io/REPO/` (creates the issues; safe to repeat)
4. `python3 tools/test_site.py --with-voting` (checks the page against a fake GitHub API)

Moderation if re-enabled: add a reply's comment ID to `site-data/hidden.json` to hide it from the page; or delete, minimise or lock it on GitHub. Votes are informal, unweighted and not sybil-resistant.

## Taking the explorer down

- Unpublish the pages: `gh api -X DELETE repos/anun333/opencl-version-explorer/pages`
- Make the repository private (Pages then stops on a free plan), or delete it: `gh repo delete anun333/opencl-version-explorer` (cannot be undone; copies and caches may persist).

## Decisions that were left open

- **AI-assistance statement.** The page footer and README say the tool was built with AI assistance and has not been reviewed by the OpenCL working group. Keep that. If you ever submit anything to a Khronos repository, read their AI-assisted-contribution statement first.

## Keeping it current

The pages are a snapshot built from the commits in `PIN`. To refresh: `./fetch.sh --latest && ./tools/regen.sh`, review the diff, commit `opencl-explorer.html`, push. The workflow redeploys. An automatic scheduled rebuild is deliberately not set up: it would publish new data without anyone reading it first.

## Check it locally first

    python3 tools/build_site.py
    python3 tools/test_site.py        # serves site/ over HTTP; checks the explorer, and that no vote page is served
