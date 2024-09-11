FROM ubuntu:22.04

# Set the timezone environment variables to avoid interaction
ENV DEBIAN_FRONTEND=noninteractive
ENV TZ=America/New_York

# Install tzdata without interaction
RUN apt-get update && apt-get install -y tzdata

# Set timezone
RUN ln -fs /usr/share/zoneinfo/America/New_York /etc/localtime && \
    dpkg-reconfigure -f noninteractive tzdata

RUN apt-get update && \
    apt-get install -y software-properties-common coreutils && \
    add-apt-repository ppa:deadsnakes/ppa && \
    apt-get update && \
    apt-get install -y git cron python3.11 python3-pip python3.11-venv && \
    python3.11 -m pip install pip --upgrade && \
    python3.11 -m venv jammy && \
    . jammy/bin/activate && \
    git clone --branch change_dependencies https://github.com/SynBioDex/SBOLExplorer.git && \
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

CMD sh -c ". ../../jammy/bin/activate && ./start.sh"
