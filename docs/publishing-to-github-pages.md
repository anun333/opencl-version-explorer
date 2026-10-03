# Publishing the explorer on GitHub Pages

Nothing here has been done for you. Publishing makes the page public and cannot be fully taken back (copies and caches persist), so these are your steps, in your account.

## Before you publish: decide these

1. **Appendix H licensing.** The *Optional features* tab shows tables from `api/appendix_h.asciidoc`, a file that states no licence. See `CREDITS.md`. Either ask Khronos, or remove those verbatim rows.
2. **What you say about AI assistance.** The README and the page footer say the tool was built with AI assistance and has not been reviewed by the OpenCL working group. Keep that. If you ever submit anything to a Khronos repository, read their AI-assisted-contribution statement first.
3. **Personal information.** The page shows one sample device by its model name only (no kernel or driver details). Remove the *Sample device* line in `tools/concerns.py` if you would rather not.
4. **Name and tone.** The title and footer say the tool is independent and not affiliated with Khronos. Check you are comfortable with the repository name too; avoid names that look official.

## Steps

1. Create an empty repository on GitHub (public, because free Pages require it).
2. In this folder: `git init`, `git add .`, `git commit`, add the remote, `git push -u origin main`.
3. In the repository: **Settings, Pages, Build and deployment, Source: GitHub Actions**.
4. The workflow `.github/workflows/pages.yml` runs on the push and publishes `site/`. The address appears in the workflow run and under Settings, Pages.

Links to a specific view work on the hosted page, for example `.../#compare?ca=v3.0.19&cb=v3.1.0`, because the view lives in the URL after the `#`. Use the *Copy link to this view* button.

## Keeping it current

The page is a snapshot built from the commits in `PIN`. To refresh: `./fetch.sh --latest && ./tools/regen.sh`, review the diff, commit the new `opencl-explorer.html`, push. The workflow deploys it. An automatic scheduled rebuild is deliberately not set up: it would publish new data without anyone reading it first.

## Check it locally first

    python3 tools/build_site.py
    python3 -m http.server 8000 --directory site      # then open http://localhost:8000/
