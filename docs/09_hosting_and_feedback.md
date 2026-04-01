# Hosting documentation & reader feedback

This project’s docs are plain Markdown under `docs/`. You can **publish them as a static site** so teammates can browse in a browser and **leave feedback** (comments or issues) to improve the content.

**Repository:** [github.com/RajnishDev-CIR/mycir_agent_using_ADK](https://github.com/RajnishDev-CIR/mycir_agent_using_ADK)

---

## Option A — Static site on GitHub Pages + Giscus comments (recommended)

**What you get:** A searchable doc site (MkDocs Material) at **`https://rajnishdev-cir.github.io/mycir_agent_using_ADK/`** (after Pages is enabled and the deploy workflow has run), with a **comment thread per page** backed by **GitHub Discussions** (no extra vendor account; works for anyone with GitHub access).

### 1. Put the repo on GitHub

Source of truth: [RajnishDev-CIR/mycir_agent_using_ADK](https://github.com/RajnishDev-CIR/mycir_agent_using_ADK). Clone or push this tree to that remote if your local folder name differs.

### 2. Enable GitHub Discussions

In the repo on GitHub: **Settings → General → Features → Discussions** (on).

### 3. Configure Giscus

1. Open [giscus.app](https://giscus.app).
2. Enter your repo name; the site checks that Discussions are enabled.
3. Choose a discussion **category** (e.g. “Documentation” or “General”).
4. Copy the generated **`repo_id`**, **`category_id`**, and mapping (e.g. **pathname** = one thread per doc page).

### 4. Turn on comments in MkDocs

Edit **`mkdocs.yml`** at the repo root:

1. Confirm **`site_url`** and **`repo_url`** in `mkdocs.yml` match your GitHub Pages URL and repo (already set for this project).
2. Adjust **`edit_uri`** if your default branch is not `main` (e.g. `edit/master/docs/`).
3. Under **`extra.comments`**, set **`enabled: true`** and add the **`provider: giscus`** block with the values from giscus.app (see the commented template in `mkdocs.yml`).

### 5. Deploy with GitHub Actions

The workflow **`.github/workflows/docs.yml`** builds the site and deploys to **GitHub Pages** on pushes to `main`.

In the repo: **Settings → Pages → Build and deployment → Source: GitHub Actions**.

After the first successful run, open the Pages URL and confirm comments load (you may need to approve the Giscus bot once on first use).

### Local preview

```bash
uv sync --group docs
uv run mkdocs serve
```

Then open `http://127.0.0.1:8000`.

---

## Option B — GitHub only (no doc site)

If you do not need a separate website:

| Goal | How |
| --- | --- |
| Suggest an edit | **Pull request** changing files under `docs/` |
| Discuss a topic | **Issue** or **Discussion** with a link to the file and line |
| Inline review | PR with “View file” — reviewers comment on the diff |

This costs nothing extra and keeps all feedback in git history.

---

## Option C — Other hosts

The same **`mkdocs build`** output (`site/` folder) can be deployed to **Azure Static Web Apps**, **Netlify**, **Cloudflare Pages**, or any static host. **Giscus** still works as long as the site URL is public and you keep the giscus configuration aligned with that origin.

For **private** docs + comments inside Microsoft 365, teams sometimes use **SharePoint** or **Confluence** and sync or paste from Markdown — that is a separate process from this repo.

---

## Summary

| Approach | Hosting | Comments / feedback |
| --- | --- | --- |
| **A** | GitHub Pages + MkDocs | Giscus → GitHub Discussions per page |
| **B** | None (repo only) | Issues, Discussions, PR review |
| **C** | Any static host | Same as A if you use Giscus |

Start with **Option A** if you want a polished site and **threaded comments** without standing up a database.
