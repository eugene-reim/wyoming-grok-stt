# wyoming-grok-stt

### Wyoming protocol Speech-to-Text server that uses the xAI Grok STT API.
The service receives audio via the Wyoming protocol, converts it to WAV, and sends it to the xAI Speech-to-Text endpoint. The resulting transcript is returned to the client.

Language is taken from the Wyoming `Transcribe` event sent by the client (e.g. Home Assistant).  
If the client does not provide a language, the server falls back to `auto` (automatic language detection by xAI).

## Requirements

- Docker
- xAI API key

## Configuration

List of supported docker environment variables

| Variable         | Default                      | Required | Description                           |
|------------------|------------------------------|----------|---------------------------------------|
| `XAI_API_KEY`    | —                            | Yes      | xAI API key                           |
| `WYOMING_URI`    | `tcp://0.0.0.0:10500`        | No       | Address the Wyoming server listens on |
| `DEBUG`          | `false`                      | No       | Enable debug logging                  |
| `XAI_STT_URL`    | `https://api.x.ai/v1/stt`    | No       | xAI STT endpoint                      |

## Run with Docker

```bash
docker run -d \
  --name wyoming-grok-stt \
  -p 10500:10500 \
  -e XAI_API_KEY=your_api_key_here \
  ghcr.io/eugene-reim/wyoming-grok-stt:latest
```

Replace `ghcr.io/eugene-reim/wyoming-grok-stt:latest` with the actual image name if you build it locally.

Build locally:

```bash
docker build -t wyoming-grok-stt .
docker run -d \
  --name wyoming-grok-stt \
  -p 10500:10500 \
  -e XAI_API_KEY=your_api_key_here \
  wyoming-grok-stt
```

## Run with Docker Compose

```yaml
services:
  wyoming-grok-stt:
    image: ghcr.io/eugene-reim/wyoming-grok-stt:latest
    container_name: wyoming-grok-stt
    ports:
      - "10500:10500"
    environment:
      - XAI_API_KEY=${XAI_API_KEY}
    restart: unless-stopped
```

Set the API key in a `.env` file or export it:

```bash
export XAI_API_KEY=your_api_key_here
```

Start the service:

```bash
docker compose up -d
```

## Usage

Point any Wyoming-compatible client (for example Home Assistant voice pipeline) to:

```
tcp://<host>:10500
```
