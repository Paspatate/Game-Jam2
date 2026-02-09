FROM python:3.14.3-slim-trixie

WORKDIR /app
RUN python3 -m venv .venv

COPY requirement.txt /app/requirements.txt

RUN .venv/bin/pip install -r requirements.txt

COPY Map/ ./Map/
COPY Assets/Backgrounds ./Assets/Backgrounds
COPY Server/ ./Server
COPY client/TmxMap.py ./Server

ENV SERVER_PORT=9999
ENV SERVER_IP=0.0.0.0
ENV SERVER_PLAYER=4
ENV SERVER_CONFIG_FROM_FILE=true

EXPOSE ${SERVER_PORT}

CMD [ "/app/.venv/bin/python", "/app/Server/Server.py" ]