import json
from unittest.mock import Mock
import httpx
import pytest
from session_watch.invites import candidate, classify_invite, page_text

CONFIG = {'llm': {'model': 'test'}, 'invites': {'enabled': True}}


def snapshot(text):
    return {'html': '<main>'+text+'</main>', 'url': 'https://example.com/dashboard', 'status': 200, 'auth_signals': []}


def mock_model(monkeypatch, result=None, offline=False):
    response=Mock();response.json.return_value={'message':{'content':json.dumps(result)}}
    if offline:response.raise_for_status.side_effect=httpx.ConnectError('offline')
    monkeypatch.setattr(httpx.Client,'post',Mock(return_value=response))


def verdict(label='interview_invite', confidence=.95, quote='New invitation from Example Residency'):
    return {'classification':label,'confidence':confidence,'reason':'New pending invitation appeared.',
            'program':'Example Residency','evidence':quote}


def test_new_invite_and_verified_quote(monkeypatch):
    mock_model(monkeypatch,verdict())
    assert classify_invite(snapshot('No pending invitations'),snapshot('New invitation from Example Residency'),CONFIG)['classification']=='interview_invite'


@pytest.mark.parametrize('result', [None, {}, verdict('not_interview_invite', .7), verdict(quote='invented evidence'), verdict(confidence=.5)])
def test_ambiguity_or_invalid_response_alerts_as_possible(monkeypatch,result):
    mock_model(monkeypatch,result)
    assert classify_invite(snapshot('Old page'),snapshot('Changed page'),CONFIG)['classification']=='possible_invite'


def test_offline_model_does_not_suppress_invite(monkeypatch):
    mock_model(monkeypatch,offline=True)
    assert classify_invite(snapshot('Old'),snapshot('New'),CONFIG)['classification']=='possible_invite'


def test_existing_invite_cannot_be_claimed_as_new(monkeypatch):
    mock_model(monkeypatch,verdict())
    old=snapshot('New invitation from Example Residency')
    assert classify_invite(old, snapshot('New invitation from Example Residency Updated date'), CONFIG)['classification']=='possible_invite'


def test_confident_unrelated_change_does_not_page(monkeypatch):
    mock_model(monkeypatch,verdict('not_interview_invite',.99,''))
    assert classify_invite(snapshot('Old layout'),snapshot('New layout'),CONFIG)['classification']=='not_interview_invite'


def test_candidate_gate_excludes_initial_login_and_invisible_script_noise():
    old=snapshot('Existing invitation<script>old token</script>')
    new=snapshot('Existing invitation<script>new token</script>')
    assert not candidate(None,new,CONFIG,{'classification':'baseline_created'},None)
    assert not candidate(old,new,CONFIG,{'classification':'uncertain'},None)
    assert candidate(old,snapshot('New pending invitation'),CONFIG,{'classification':'uncertain'},None)
    assert candidate(old,new,CONFIG,{'classification':'uncertain'},{'classification':'visual_change'})
    assert not candidate(old,new,CONFIG,{'classification':'auth_expired'},{'classification':'visual_change'})


def test_counter_increase_overrides_overconfident_negative(monkeypatch):
    mock_model(monkeypatch,verdict('not_interview_invite',.99,''))
    old=snapshot('Total Invitations\n14\nInvitations Pending\n0')
    new=snapshot('Total Invitations\n15\nInvitations Pending\n1')
    assert classify_invite(old,new,CONFIG)['classification']=='possible_invite'


def test_unexplained_pixel_change_cannot_be_ruled_out_by_text_model(monkeypatch):
    mock_model(monkeypatch,verdict('not_interview_invite',.99,''))
    old=snapshot('Same text')
    assert classify_invite(old,old,CONFIG,{'classification':'visual_change'})['classification']=='possible_invite'
