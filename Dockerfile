FROM ubuntu:18.04

ARG DEBIAN_FRONTEND=noninteractive

RUN apt-get update && \
    apt-get install -y --no-install-recommends  software-properties-common \
    wget && \
    add-apt-repository ppa:deadsnakes/ppa && \
    apt-get update && \
    apt-get install -y \
    build-essential \
    python3.9 \
    python3.9-dev \
    python3.9-distutils \
    python3-pip && \
    rm -rf /var/lib/apt/lists/*

# update pip
RUN python3.9 -m pip install pip --upgrade && \
    python3.9 -m pip install wheel  && \
    python3.9 -m pip install --upgrade setuptools && \
    python3.9 -m pip install --upgrade distlib

# install the requirements
COPY requirements.txt .
RUN pip3 install --no-cache --upgrade  -r requirements.txt

# expose the port
EXPOSE 8082

# copy the contents into an image and set working direcotry
COPY data_server /opt/data-server/data_server
WORKDIR /opt/data-server/data_server

CMD ["python3.9", "-u", "app.py"]