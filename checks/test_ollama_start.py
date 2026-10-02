from unittest.mock import Mock
from server.api import server
from server.core import system_check
import subprocess

def test_running_ollama_is_not_started_again(monkeypatch):
    monkeypatch.setattr(system_check,'detect_ollama',lambda:{'installed':True,'running':True})
    launch=Mock();monkeypatch.setattr(subprocess,'Popen',launch)
    assert server.start_local_ollama()['running']
    launch.assert_not_called()

def test_explicit_start_uses_detected_executable_without_shell(monkeypatch):
    statuses=iter([{'installed':True,'running':False,'executable':'local-ollama.exe'}, {'running':True}])
    monkeypatch.setattr(system_check,'detect_ollama',lambda:next(statuses))
    launch=Mock();monkeypatch.setattr(subprocess,'Popen',launch)
    assert server.start_local_ollama()['running']
    assert launch.call_args.args[0]==['local-ollama.exe','serve']
    assert not launch.call_args.kwargs.get('shell')
