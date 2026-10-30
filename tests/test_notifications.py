import unittest
from scripts.notify_issues import build_notification

class TestNotifications(unittest.TestCase):
    def test_new_role_issue(self):
        title,body=build_notification({'type':'new','company':'Clifford Chance','title':'Dubai Vacation Scheme','jobId':'cc:1','url':'https://jobs.smartrecruiters.com/CliffordChance/123','detectedAt':'2026-10-30T00:00:00Z'})
        self.assertIn('New legal vacancy',title)
        self.assertIn('Official application link',body)
        self.assertIn('law-atlas:new:cc:1',body)
    def test_deadline_change_report(self):
        _,body=build_notification({'type':'deadline_changed','company':'Test','title':'Paralegal','jobId':'cc:3','previous':'2026-11-10','deadline':'2026-11-20','url':'https://example.com/job'})
        self.assertIn('2026-11-20',body)
        self.assertIn('2026-11-10',body)
    def test_no_notification_for_unsupported_event(self):
        self.assertIsNone(build_notification({'type':'page_hash_changed'}))

if __name__=='__main__':unittest.main()
