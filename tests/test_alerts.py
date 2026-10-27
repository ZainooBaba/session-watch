from unittest.mock import Mock
import subprocess
import pytest
from session_watch.alerts import alert_kind, play_alert


@pytest.mark.parametrize('result,expected', [
    ({'classification':'auth_expired','visual':{'classification':'visual_change'}}, 'login'),
    ({'classification':'content_change'}, 'change'),
    ({'classification':'uncertain','visual':{'classification':'visual_change'}}, 'change'),
    ({'classification':'uncertain'}, None),
    ({'classification':'unchanged','visual':{'classification':'visually_unchanged'}}, None),
    ({'classification':'baseline_created'}, None),
])
def test_alert_selection(result, expected):
    assert alert_kind(result)==expected


def test_disabled_alerts_do_not_launch_player(monkeypatch):
    player=Mock();monkeypatch.setattr(subprocess,'run',player)
    assert play_alert({}, {'classification':'auth_expired'}) is None
    player.assert_not_called()


@pytest.mark.parametrize('label,sound,repeats',[('auth_expired','Basso',3),('content_change','Glass',2)])
def test_distinct_sounds(monkeypatch,label,sound,repeats):
    monkeypatch.setattr('session_watch.alerts.sys.platform','darwin')
    player=Mock();monkeypatch.setattr(subprocess,'run',player)
    result=play_alert({'alerts':{'enabled':True}},{'classification':label})
    assert result['played'] and player.call_count==repeats
    assert player.call_args.args[0][-1].endswith(sound+'.aiff')
    assert player.call_args.args[0][2] == '1.0'


def test_failed_audio_is_nonfatal(monkeypatch):
    monkeypatch.setattr('session_watch.alerts.sys.platform','darwin')
    monkeypatch.setattr(subprocess,'run',Mock(side_effect=OSError('unavailable')))
    result=play_alert({'alerts':{'enabled':True}},{'classification':'auth_expired'})
    assert not result['played'] and result['error']


def test_invite_only_mode_alerts_for_possible_but_not_generic_changes():
    assert alert_kind({'classification':'content_change'},invite_only=True) is None
    assert alert_kind({'classification':'uncertain','invite':{'classification':'possible_invite'}},invite_only=True)=='change'
    assert alert_kind({'classification':'content_change','invite':{'classification':'not_interview_invite'}},invite_only=True) is None
    assert alert_kind({'classification':'auth_expired'},invite_only=True)=='login'
