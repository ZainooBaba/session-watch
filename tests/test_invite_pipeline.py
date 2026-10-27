import json
from unittest.mock import Mock
from session_watch.cli import check
from session_watch import invites

CONFIG={'llm':{'model':'test'},'invites':{'enabled':True},'alerts':{'enabled':False,'invite_only':True}}


def page(text):
    return {'html':'<main>'+text+'</main>','url':'https://example.com/dashboard','status':200,'auth_signals':[]}


def test_uncertain_first_layer_runs_invite_pass_but_possible_stays_local(tmp_path,monkeypatch):
    (tmp_path/'baseline.json').write_text(json.dumps(page('No pending invitations')))
    browser=Mock();browser.capture.return_value=page('One pending invitation')
    monkeypatch.setattr('session_watch.cli.decide',lambda *a:{'classification':'uncertain','confidence':.4,'reason':'Unsure','advance':False})
    classify=Mock(return_value={'classification':'possible_invite','confidence':.4,'reason':'May be new.','program':'','evidence':''})
    monkeypatch.setattr(invites,'classify_invite',classify)
    check(CONFIG,tmp_path,browser)
    classify.assert_called_once()
    analysis=json.loads((tmp_path/'latest-analysis.json').read_text())
    assert analysis['stage1']['classification']=='uncertain'
    assert analysis['stage2']['classification']=='possible_invite'
    assert analysis['pager_event_id'] is None
    assert not list((tmp_path/'pager-outbox').glob('*.json'))
    assert 'One pending' in (tmp_path/'baseline.json').read_text()
    browser.save.assert_called_once()


def test_login_never_runs_invite_pass_or_pages(tmp_path,monkeypatch):
    (tmp_path/'baseline.json').write_text(json.dumps(page('Dashboard')))
    browser=Mock();browser.capture.return_value=page('Sign in')
    monkeypatch.setattr('session_watch.cli.decide',lambda *a:{'classification':'auth_expired','reason':'Login','advance':False})
    classify=Mock();monkeypatch.setattr(invites,'classify_invite',classify)
    assert check(CONFIG,tmp_path,browser)=='auth_expired'
    classify.assert_not_called()
    assert not list((tmp_path/'pager-outbox').glob('*.json'))
    assert 'Dashboard' in (tmp_path/'baseline.json').read_text()


def test_confident_non_invite_change_is_visible_but_does_not_page(tmp_path,monkeypatch):
    (tmp_path/'baseline.json').write_text(json.dumps(page('Old date')))
    browser=Mock();browser.capture.return_value=page('Updated date')
    monkeypatch.setattr('session_watch.cli.decide',lambda *a:{'classification':'content_change','confidence':1,'reason':'Date updated','advance':True})
    monkeypatch.setattr(invites,'classify_invite',lambda *a:{'classification':'not_interview_invite','confidence':.99,'reason':'Existing interview rescheduled','program':'','evidence':''})
    check(CONFIG,tmp_path,browser)
    assert not list((tmp_path/'pager-outbox').glob('*.json'))
    analysis=json.loads((tmp_path/'latest-analysis.json').read_text())
    assert analysis['stage2']['reason']=='Existing interview rescheduled'


def test_confirmed_new_invite_is_the_only_pager_candidate(tmp_path,monkeypatch):
    (tmp_path/'baseline.json').write_text(json.dumps(page('No pending invitation')))
    browser=Mock();browser.capture.return_value=page('New interview invitation')
    monkeypatch.setattr('session_watch.cli.decide',lambda *a:{'classification':'content_change','confidence':1,'reason':'A row appeared','advance':True})
    monkeypatch.setattr(invites,'classify_invite',lambda *a:{'classification':'interview_invite','confidence':.95,
        'reason':'New interview invitation appeared','program':'Example','evidence':'New interview invitation'})
    check(CONFIG,tmp_path,browser)
    analysis=json.loads((tmp_path/'latest-analysis.json').read_text())
    assert analysis['pager_event_id']
    assert len(list((tmp_path/'pager-outbox').glob('*.json')))==1
