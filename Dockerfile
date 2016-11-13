FROM gliderlabs/alpine:3.3

RUN apk add --update \
    python3 \
    python3-dev \
    build-base \
    ca-certificates \
  && python3 -m ensurepip \
  && pip3 install virtualenv \
  && rm -rf /var/cache/apk/*

WORKDIR /app

COPY . /app
RUN virtualenv /env && /env/bin/pip3 install -e .

CMD ["/env/bin/python", "slack_consul"]
