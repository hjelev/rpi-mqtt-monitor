FROM python:3.8-slim-buster
RUN apt-get update
RUN apt-get -y install cron

WORKDIR /app
COPY . /app

RUN pip install paho-mqtt
RUN echo "*/2 * * * * /usr/local/bin/python /app/src/rpi-cpu2mqtt.py > /proc/1/fd/1 2>/proc/1/fd/2" > /etc/cron.d/crontab
RUN chmod 0644 /etc/cron.d/crontab
RUN /usr/bin/crontab /etc/cron.d/crontab
CMD ["cron", "-f"]

