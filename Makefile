.PHONY: docker-full-up audio-agent-configure audio-agent-build audio-agent-run audio-worker-test-chunk

docker-full-up:
	docker compose --profile full up --build

audio-agent-configure:
	cd native/desktop-agent && cmake -S . -B build -DCMAKE_BUILD_TYPE=Release

audio-agent-build:
	cd native/desktop-agent && cmake --build build --config Release

audio-agent-run:
	powershell -NoProfile -ExecutionPolicy Bypass -Command "& '.\native\desktop-agent\build\Release\grey-cardinal-agent.exe' --server http://localhost:8020 --token dev-internal-token --meeting-id demo-meeting"

audio-worker-test-chunk:
	powershell -NoProfile -ExecutionPolicy Bypass -File .\apps\audio-worker\scripts\send_mock_wav.ps1 -Server http://localhost:8020 -Token dev-internal-token -MeetingId demo-meeting

