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


def thalamus(invites, interviews=''):
    return snapshot('<thal-dashboard-invites>'+invites+'</thal-dashboard-invites><thal-dashboard-events>'+interviews+'</thal-dashboard-events>')


def test_empty_invites_rejects_scheduled_row_hallucination(monkeypatch):
    quote='Example Residency 1st Interview Mon Nov 16 Scheduled Not published'
    mock_model(monkeypatch,verdict(quote=quote))
    before=thalamus('<div aria-busy="true">Loading invites</div>', '<div id="dashboard-interviews-loading-container">Loading</div>')
    after=thalamus('Invites No invites yet',quote)
    result=classify_invite(before,after,CONFIG,{'classification':'visual_change'})
    assert result['classification']=='not_interview_invite'
    assert 'No invites yet' in result['reason']


def test_unchanged_invites_rejects_changes_elsewhere(monkeypatch):
    mock_model(monkeypatch,verdict())
    before=thalamus('Existing invitation from Example Residency','Scheduled table one')
    after=thalamus('Existing invitation from Example Residency','Scheduled table two')
    assert classify_invite(before,after,CONFIG)['classification']=='not_interview_invite'


def test_new_invite_panel_gets_focused_diff_and_remains_confirmable(monkeypatch):
    response=Mock();response.json.return_value={'message':{'content':json.dumps(verdict())}}
    post=Mock(return_value=response);monkeypatch.setattr(httpx.Client,'post',post)
    before=thalamus('No invites yet','Old scheduled event')
    after=thalamus('New invitation from Example Residency','Old scheduled event')
    result=classify_invite(before,after,CONFIG)
    assert result['classification']=='interview_invite'
    payload=json.loads(post.call_args.kwargs['json']['messages'][1]['content'])
    assert payload['comparison_scope']=='invites_panel'
    assert 'New invitation' in payload['added_text']
    assert 'No invites yet' in payload['removed_text']
    assert 'Old scheduled event' not in payload['current_text']
    choices=post.call_args.kwargs['json']['format']['properties']['evidence']['enum']
    assert 'New invitation from Example Residency' in choices
    assert '' in choices
