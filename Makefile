.PHONY: test test-python test-agent docker-full-up audio-agent-configure audio-agent-build audio-agent-test audio-agent-run audio-worker-test-chunk

test: test-python test-agent

test-python:
	python -m pytest apps/audio-worker apps/brain-api

test-agent: audio-agent-configure audio-agent-build audio-agent-test

docker-full-up:
	docker compose --profile full up --build

audio-agent-configure:
	cd native/desktop-agent && cmake -S . -B build -DCMAKE_BUILD_TYPE=Release

audio-agent-build:
	cd native/desktop-agent && cmake --build build --config Release

audio-agent-test:
	cd native/desktop-agent && ctest --test-dir build --output-on-failure -C Release

audio-agent-run:
	powershell -NoProfile -ExecutionPolicy Bypass -Command "& '.\native\desktop-agent\build\Release\grey-cardinal-agent.exe' --server http://localhost:8020 --token dev-internal-token --meeting-id demo-meeting"

audio-worker-test-chunk:
	powershell -NoProfile -ExecutionPolicy Bypass -File .\apps\audio-worker\scripts\send_mock_wav.ps1 -Server http://localhost:8020 -Token dev-internal-token -MeetingId demo-meeting
