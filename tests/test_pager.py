import json
from unittest.mock import Mock
import httpx
from session_watch import pager

INVITE={'classification':'interview_invite','confidence':.95}
POSSIBLE={'classification':'possible_invite','confidence':0}
KEY='a'*32


def configured(tmp_path):
    pager.save_settings(tmp_path,KEY)


def test_no_destination_keeps_alert_pending_without_sending(tmp_path,monkeypatch):
    player=Mock();monkeypatch.setattr(httpx.Client,'post',player)
    pager.queue(tmp_path,'event',INVITE)
    pager.dispatch(tmp_path,{})
    assert pager.status(tmp_path,{},'event')['delivery']['status']=='pending'
    player.assert_not_called()


def test_successful_delivery_is_deduplicated_and_minimal(tmp_path,monkeypatch):
    configured(tmp_path)
    response=Mock(status_code=202);response.json.return_value={'status':'success'}
    send=Mock(return_value=response);monkeypatch.setattr(httpx.Client,'post',send)
    pager.queue(tmp_path,'event',INVITE);pager.queue(tmp_path,'event',INVITE)
    pager.dispatch(tmp_path,{});pager.dispatch(tmp_path,{})
    assert send.call_count==1
    args=send.call_args
    assert args.args[0]==pager.ENDPOINT
    payload=args.kwargs['json']
    assert payload['dedup_key']=='session-watch-event'
    assert payload['event_action']=='trigger' and payload['payload']['severity']=='critical'
    assert 'html' not in json.dumps(payload) and 'reason' not in json.dumps(payload)
    assert pager.status(tmp_path,{},'event')['delivery']['status']=='accepted'
    assert KEY not in json.dumps(pager.status(tmp_path,{}))


def test_failed_delivery_stays_queued_with_backoff(tmp_path,monkeypatch):
    configured(tmp_path)
    response=Mock();response.raise_for_status.side_effect=httpx.ConnectError('offline')
    send=Mock(return_value=response);monkeypatch.setattr(httpx.Client,'post',send)
    pager.queue(tmp_path,'event',INVITE)
    pager.dispatch(tmp_path,{});pager.dispatch(tmp_path,{})
    assert send.call_count==1
    delivery=pager.status(tmp_path,{},'event')['delivery']
    assert delivery['status']=='pending' and delivery['next_attempt_at']>0
    record=tmp_path/'pager-outbox/event.json'
    data=json.loads(record.read_text());data['next_attempt_at']=0;record.write_text(json.dumps(data))
    response.raise_for_status.side_effect=None;response.status_code=202;response.json.return_value={'status':'success'}
    pager.dispatch(tmp_path,{})
    assert pager.status(tmp_path,{},'event')['delivery']['status']=='accepted'


def test_signout_pauses_pager_and_unrelated_results_never_queue(tmp_path,monkeypatch):
    configured(tmp_path);(tmp_path/'signed-out').write_text('yes')
    send=Mock();monkeypatch.setattr(httpx.Client,'post',send)
    assert pager.queue(tmp_path,'unrelated',{'classification':'not_interview_invite'}) is None
    assert pager.queue(tmp_path,'possible',POSSIBLE) is None
    pager.queue(tmp_path,'new-invite',INVITE);pager.dispatch(tmp_path,{})
    send.assert_not_called()
    assert (tmp_path/'pager-settings.json').stat().st_mode & 0o077==0


def test_possible_and_legacy_unconfirmed_outbox_items_never_reach_pagerduty(tmp_path,monkeypatch):
    configured(tmp_path)
    send=Mock();monkeypatch.setattr(httpx.Client,'post',send)
    assert pager.queue(tmp_path,'possible',POSSIBLE) is None
    folder=tmp_path/'pager-outbox';folder.mkdir(exist_ok=True)
    (folder/'legacy.json').write_text(json.dumps({'id':'legacy','classification':'possible_invite','confidence':.5,
        'status':'pending','attempts':0,'next_attempt_at':0,'created_at':'2026-10-27T15:00:00Z'}))
    pager.dispatch(tmp_path,{})
    send.assert_not_called()
    assert json.loads((folder/'legacy.json').read_text())['status']=='local_only'
    assert pager.status(tmp_path,{})['pending_count']==0
