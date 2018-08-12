FROM ubuntu:16.04
MAINTAINER Michael Zhang <michael13162@gmail.com>

RUN apt-get update && \
  apt-get install -y software-properties-common && \
  add-apt-repository ppa:jonathonf/python-3.6 && \
  apt-get update && \
  apt-get install -y git python3.6 python3-pip && \
  python3.6 -m pip install pip --upgrade && \
  git clone https://github.com/michael13162/SBOLExplorer.git && \
  cd SBOLExplorer/flask && \
  pip install -r requirements.txt && \
  crontab update.cron

WORKDIR /SBOLExplorer/flask

ENV LC_ALL=C.UTF-8
ENV LANG=C.UTF-8

EXPOSE 13162

CMD "./start.sh"

