# Publishing: what is live, and how to take it down

## What was published (2026-10-03)

- Repository: https://github.com/anun333/opencl-version-explorer (public; free Pages require that)
- Explorer: https://anun333.github.io/opencl-version-explorer/
- Voting page: https://anun333.github.io/opencl-version-explorer/vote.html
- 14 direction issues and 40 concern issues, created by `tools/seed_votes.py`.

## How voting and replies work

There is no server. Each direction is a GitHub issue and **each votable concern is its own issue** (14 directions and 40 concerns, created by `tools/seed_votes.py`). A vote is a GitHub reaction (👍 or 👎) on the issue, so voters are people with GitHub accounts, one reaction per person per item. A **reply** is an ordinary comment on that issue; `vote.html` shows replies under the item with the author's GitHub name (plain text, shortened to 600 characters, with a link to the full comment). It reads issues and comments from the GitHub API in the visitor's browser and caches them for five minutes (anonymous API calls are limited to 60 per hour per address).

It trusts only issues written by the repository owner that carry the hidden markers `<!-- vote-direction: ID -->` or `<!-- vote-item: ID -->`, so a stray issue cannot add a line or fake a count. Anyone may reply; replies on issues that are not items are ignored.

What a vote means: on a direction, 👍 = I would want this explored for a future version; on a concern, 👍 = I agree it is a real concern and 👎 = I do not think so or think it is wrong. It is an informal, unweighted poll with no authority. Reactions are not sybil-resistant: anyone can create accounts.

**Moderation.** To hide a reply from the vote page without deleting it, add its comment ID (the number after `issuecomment-` in its link) to `site-data/hidden.json`, e.g. `{"comments": [123456789]}`, commit and push. You can also delete, minimize or lock comments on GitHub, or block a user.

Line items are identified by a hash of the direction and the concern text, shown on the page next to each item (with a copy-link button). If the data is regenerated and a line's wording changes, it becomes a new item and starts at zero; `seed_votes.py` only adds what is missing and never deletes (except `--migrate`, a one-time clean-up of the first layout).

## Things to know as the owner

- GitHub emails you about new reactions, comments and issues on your repository (54 issues now exist). Adjust under Settings, Notifications, or watch settings on the repository.
- Anyone can comment on the issues, and their replies (with their GitHub names) are shown on the vote page unless you hide them. You are the moderator.
- The page shows anonymous visitors only counts; they vote by following the link to GitHub and signing in.

## Decisions that were left open

1. **Appendix H licensing.** The *Optional features* tab shows tables from `api/appendix_h.asciidoc`, a file that states no licence (see `CREDITS.md`). If you want to remove them: edit `tools/extract_optional.py` or blank the `rows` in `data/optional.json`, rebuild, push.
2. **AI-assistance statement.** The page footer and README say the tool was built with AI assistance and has not been reviewed by the OpenCL working group. Read Khronos's own AI-assisted-contribution statement before submitting anything to their repositories.

## Taking it down

- Unpublish the pages only: `gh api -X DELETE repos/anun333/opencl-version-explorer/pages`
- Close the poll: close or delete the 14 issues, or make the repository private (Pages then stops on a free plan).
- Remove everything: `gh repo delete anun333/opencl-version-explorer` (cannot be undone; copies and caches may persist).

## Keeping it current

The pages are a snapshot built from the commits in `PIN`. To refresh: `./fetch.sh --latest && ./tools/regen.sh`, review the diff, commit `opencl-explorer.html` and `site-data/concerns.json`, push. The workflow redeploys. After a refresh, run `python3 tools/seed_votes.py anun333/opencl-version-explorer --site-url https://anun333.github.io/opencl-version-explorer/` to add any new concern lines. An automatic scheduled rebuild is deliberately not set up: it would publish new data without anyone reading it first.

## Check it locally first

    python3 tools/build_site.py --repo anun333/opencl-version-explorer
    python3 tools/test_site.py        # serves site/ over HTTP, uses a fake GitHub API for the vote page
