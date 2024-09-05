FROM ubuntu:22.04
MAINTAINER Michael Zhang <michael13162@gmail.com>

RUN apt-get update && \
    apt-get install -y software-properties-common && \
    add-apt-repository ppa:deadsnakes/ppa && \
    apt-get update && \
    apt-get install -y git python python-pip && \
    python -m pip install pip --upgrade && \
    git clone https://github.com/michael13162/SBOLExplorer.git && \
    cd SBOLExplorer/flask && \
    pip install -r requirements.txt && \
    crontab update.cron

WORKDIR /SBOLExplorer/flask

ENV LC_ALL=C.UTF-8
ENV LANG=C.UTF-8

EXPOSE 13162

RUN mkdir /mnt/config && \
    mkdir /mnt/data && \
    mv config.json /mnt/config && \ 
    ln -s /mnt/config/config.json config.json && \
    rm -rf dumps && \
    ln -s /mnt/data dumps

CMD "./start.sh"

