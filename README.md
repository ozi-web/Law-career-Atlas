# Law Career Atlas 2027 — Dubai / DIFC / UK & International Big Law

A searchable job and application dashboard for international firms and established regional law firms, designed for an applicant with a UK Corporate Law LLM who is **not a UAE national**. The site is separate from the finance Career Atlas project.

## What is in this release

- **111 curated firm profiles**, mostly UK and US international firms, plus established regional firms. A DIFC office is not the same as DIFC Courts registered-practitioner status. This directory is not an exhaustive list of all DIFC firms.
- **8 dated official programme references**, curated as of 30 October 2026; they are not automatically guaranteed to remain open. Check their source URLs before applying.
- **65 configured official law-firm recruitment sources**: **1 verified structured public jobs API** for Clifford Chance through SmartRecruiters and **64 partial HTML/JSON-LD career-page checks**. The other **46 firms are portal links only**.
- Additional tested source adapters for **Greenhouse, Ashby and Lever**. These are available for adding a firm **only after verifying that its real official public board uses the provider**. The current directory does not falsely claim those providers are enabled for every firm.
- The collector records individual job IDs, title, employer, location, official application URL, published date when available, explicit deadline when published, first detected date, last successful check, and source status.
- Newly discovered roles and genuine employer-feed deadline changes are recorded as events. A missed listing requires **two consecutive successful full-feed checks** before being marked *not in latest feed*. A failed feed or partial page check never proves a job is closed.
- Status and coverage dashboard distinguishes **structured feed**, **partial page extraction**, **failed check**, and **career-link only**. Successful HTML access does **not** mean all that firm's jobs were found.
- Company search, firm profiles, saved firms, programme and live-role filters, new-since-last-visit view, per-job Applied checkboxes, application stage, notes, interview tracking, follow-up dates, and private JSON/CSV exports.
- No GitHub deployment or setup checklist is shown on the public website. Setup directions live **only in this README**.

### A crucial limitation

**No version of this tracker can guarantee every vacancy across all 111 firms.** Large firms use many different applicant-tracking systems, sometimes block automated requests, and sometimes publish roles only through client-side scripts. Public recruitment APIs may not expose deadlines or the full eligibility rules. The 64 partial page monitors detect only machine-readable `JobPosting` records exposed by the public HTML. They must **not** be called complete vacancy coverage. The live data file starts unverified; the first scheduled workflow must run after deployment.

## GitHub Pages: setup (not displayed on public site)

1. Create a *separate* public GitHub repository, such as `Law-Career-Atlas`. Leave GitHub's README initialization off if uploading the package as-is.
2. Unzip the final package, open the resulting folder, and upload **all its contents** to the repository root. On a Mac, press **Command + Shift + .** to reveal the hidden `.github` directory. The repository must have `.github/workflows/check-law-careers.yml` in exactly that path.
3. Choose **Settings → Pages → Build and deployment → GitHub Actions**. Do not select branch deployment because the scheduled workflow explicitly publishes the refreshed website.
4. Under **Settings → Actions → General**, enable Actions. Select **Read and write permissions** for workflow tokens. The workflow declares `contents: write`, `pages: write`, `id-token: write`, and `issues: write`. Leave Issues enabled if you want role-change notifications through GitHub Issues.
5. Go to **Actions → Update law vacancies and publish Career Atlas → Run workflow**. The first run tests the collector, checks the configured sources, updates `data/live_jobs.json`, builds the website and deploys it. The first baseline **does not create issue alerts for every existing posting**.
6. Visit `https://YOUR-USERNAME.github.io/Law-Career-Atlas/`, open **Monitoring** and confirm how many structured, partial and failed checks are reported. New job postings appear in **Openings** only if one of the configured integrations captures them.
7. For GitHub Issue notifications, click **Watch → Custom → Issues** on the repository. Notifications depend on your GitHub notification settings and Issues availability. Alerts are created only for new job IDs, published deadline changes or confirmed absence from a fully enumerated feed. If Issues cannot be created, workflow still deploys and the Actions summary contains changes.

The scheduled workflow runs **daily at approximately 08:23 Dubai time** (04:23 UTC). GitHub may delay scheduled runs or disable them on inactive repositories.

## How automated data works

| Mode | Configured | What is reliable | Limit |
|---|---:|---|---|
| SmartRecruiters API | Clifford Chance | Published job IDs and titles, location, direct application links; deadlines only when explicit | Does not cover other employers |
| Greenhouse API | Adapter ready | Published jobs from verified company-specific boards | Not enabled without a real, verified board ID |
| Ashby public board API | Adapter ready | Listed published jobs | Not enabled without a verified board name |
| Lever postings API | Adapter ready | Published postings from an identified board | Not enabled without a verified board name |
| Official career-page JSON-LD | 64 firms | `JobPosting` records embedded in accessible HTML | Most career sites do not expose all vacancies in JSON-LD; *partial* only |
| Directory-only links | 46 firms | Official career-page navigation | **No automated vacancy discovery** |

**Deadline policy:** A deadline is shown as employer-published only if a structured source provides an explicit parseable deadline. Missing deadlines stay blank. An older published deadline is retained with a **recheck** warning when a feed stops displaying it. Curated reference programme deadlines are not silently updated by generic page changes.

**Eligibility:** Nationwide-only and Emiratisation-only schemes may be restricted to nationals. The collector flags explicit restrictions when the text is exposed, but the applicant must verify the entire job description. An LLM by itself does **not** qualify someone as an England & Wales solicitor; consult the [SRA](https://www.sra.org.uk/become-solicitor/sqe/) for the SQE and QWE requirements. DIFC Courts practitioner registration is a separate issue: [official register](https://eregistry.difccourts.ae/practitioners).

## Adding verified employer feeds

Edit `config/job_sources.json` and add **one proven public employer-specific endpoint**. Examples (illustrative, **not** real board identifiers for these firms):

```json
{"id":"verified-firm-board","firmId":"existing-firm-id","company":"Firm name","provider":"greenhouse","identifier":"ACTUAL_PUBLIC_BOARD_TOKEN"}
```

Valid `provider` values are `smartrecruiters`, `greenhouse`, `ashby`, `lever`, and `html-jsonld`. Every source must link to a firm ID in `data/firms.json`. `html-jsonld` entries need an official `url`, not an arbitrary generic search engine. Do not add guessed API slugs or bypass CAPTCHAs or access controls. Test a real fetch before claiming a feed works.

Relevant official API documentation:

- SmartRecruiters: https://developers.smartrecruiters.com/docs/endpoints
- Greenhouse: https://docs.greenhouse.io/job-board
- Ashby: https://developers.ashbyhq.com/docs/public-job-posting-api
- Lever: https://github.com/lever/postings-api

## Project structure

- `index.html` — standalone preview and published GitHub Pages website
- `index.template.html`, `scripts/app.js`, `scripts/build_site.py` — interface and static builder
- `data/firms.json` — curated employer directory
- `data/opportunities.json` — 2027 programme reference entries (not automatically reverified)
- `config/job_sources.json` — official monitoring sources
- `scripts/collect_jobs.py` — public job-feed adapters and conservative reconciler
- `data/live_jobs.json` — last results, event changes, monitoring coverage and failure diagnostics
- `scripts/notify_issues.py` — optional public GitHub Issue job-change alerts and workflow summary
- `.github/workflows/check-law-careers.yml` — scheduled test, collection, commit and explicit Pages deployment
- `tests/` — offline regression tests with synthetic recruitment feeds

## Local testing

From the repository root:

```bash
python -m unittest discover -s tests -v
python scripts/build_site.py
```

`python scripts/collect_jobs.py` **requires network access** to the public recruitment sites; local offline regression tests validate parsers and reconciliation but do not prove live external feed availability. Inspect the workflow run and **Monitoring** panel after deployment before relying on new-job alerts.

## Privacy

Your applications, notes and recruiter contacts are stored using browser-local storage, not committed to this public repository. Export JSON in the **Notes & guidance** page to back up or move them. Don't upload your private backup or CV to GitHub. Different browsers and devices don't synchronize notes automatically.
