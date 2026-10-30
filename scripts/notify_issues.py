"""Optional GitHub Issues notifications for new UAE law roles and deadline changes.

GitHub Issues notifications require the repository owner to subscribe to Issues.
Errors do not stop the scheduled website deployment. No user application data used.
"""
from __future__ import annotations
import json
import os
import subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]


def build_notification(event):
    typ=event.get('type')
    if typ not in ('new','deadline_changed','unlisted'):
        return None
    label={'new':'New legal vacancy','deadline_changed':'Job deadline changed','unlisted':'Listing absent from verified feed'}[typ]
    title=f"[Law Atlas] {label}: {event.get('company','')} — {event.get('title','')}"[:245]
    lines=[f"**Firm:** {event.get('company','')}",f"**Role:** {event.get('title','')}",
           f"**Official application link:** {event.get('url','')}",
           f"**Detected (UTC):** {event.get('detectedAt','')}"]
    if typ=='deadline_changed':
        lines.extend([f"**Previous published deadline:** {event.get('previous','')}",
                      f"**New published deadline:** {event.get('deadline','')}"])
    elif event.get('deadline'):
        lines.append(f"**Employer-published deadline:** {event['deadline']}")
    if typ=='unlisted':
        lines.append('The listing was absent from two consecutive successful checks of the same official job feed. This does not conclusively prove that recruiting has closed.')
    lines.append('This is an automated public job-feed notice. Confirm eligibility and application status directly with the employer. No personal application notes are transmitted.')
    lines.append(f"<!-- law-atlas:{typ}:{event.get('jobId','')}:{event.get('detectedAt','')} -->")
    return title,'\n\n'.join(lines)


def run(path=None, command_runner=subprocess.run):
    path=Path(path or ROOT/'data/live_jobs.json')
    doc=json.loads(path.read_text(encoding='utf-8'))
    events=doc.get('events',[])
    summary=os.environ.get('GITHUB_STEP_SUMMARY')
    if summary:
        with open(summary,'a',encoding='utf-8') as f:
            f.write(f"### Law Career Atlas recruitment checks\n\n- Configured sources: {doc.get('meta',{}).get('configuredSources',0)}\n- Successful structured feeds: {doc.get('meta',{}).get('verifiedFeedsSuccessful',0)}\n- Limited career pages: {doc.get('meta',{}).get('limitedPageChecks',0)}\n- Failed sources: {doc.get('meta',{}).get('failedSources',0)}\n- New relevant postings: {doc.get('meta',{}).get('newRolesLastRun',0)}\n- Deadline changes: {doc.get('meta',{}).get('deadlineChangesLastRun',0)}\n\n")
            for e in events[:15]:f.write(f"- {e.get('type','')} — {e.get('company','')}: [{e.get('title','')}]({e.get('url','')})\n")
    if not events:
        print('No changes; no GitHub Issues to create.')
        return 0
    if not os.environ.get('GH_TOKEN') or not os.environ.get('GITHUB_REPOSITORY'):
        print('GitHub Issue alerts unavailable (missing authenticated repository context).')
        return 0
    count=0
    for ev in events[:15]:
        note=build_notification(ev)
        if not note:
            continue
        title,body=note
        try:
            # Mark title and body clearly as automated; GitHub notifications depend
            # on the owner's Watch preferences and Issues being enabled.
            r=command_runner(['gh','issue','create','--title',title,'--body',body],
                             capture_output=True,text=True,timeout=25,check=False)
            if r.returncode==0:
                count+=1
                print('Created Issue alert: '+title)
            else:
                print('Issue notification unavailable: '+r.stderr.strip()[:200])
        except (FileNotFoundError,subprocess.TimeoutExpired) as exc:
            print(f'Issue notification unavailable: {exc}')
    return count


if __name__=='__main__':
    run()
