# home-server-docker-compose

<!-- Each Image should have a link to the dockerhub page and some documentation (git, starter guide, etc.) -->

## docker-compose.yml

This is the base infrastructure using SWAG, DuckDNS, and Duplicati

### Swag (Secure Web Application Gateway)

A combination of Nginx, Certbot, PHP, and Fail2Ban. Check out the [SWAG starter guide](https://blog.linuxserver.io/2019/04/25/letsencrypt-nginx-starter-guide/#creatingaletsencryptcontainer).
P.S. it used to be called letsencrypt. Here's the 
[SWAG Docker image documentation](https://hub.docker.com/r/linuxserver/swag).

#### Nginx

Reverse proxy

#### Certbot

Free, auto-renewing SSL

#### PHP

Hosting webpages

#### Fail2ban

Intrustion prevention, since you're exposed... to the internet

### DuckDNS

Since my Google WiFi routers don't support Dynamic DNS, I use [DuckDNS](https://www.duckdns.org/) to bind my public IP to a DuckDNS DNS and then use the [DuckDNS Docker image](https://hub.docker.com/r/linuxserver/duckdns/) to update my public DNS to DuckDNS every five minutes.

## media-compose.yml

Coming Soon

[Tautulli](https://github.com/Tautulli/Tautulli)

## elk-compose.yml

In Progress...

[This](https://github.com/deviantony/docker-elk) helped a lot

[Running the Elastic Stack on Docker](https://www.elastic.co/guide/en/elastic-stack-get-started/current/get-started-docker.html)

#### Logstash
Check [this](https://www.elastic.co/guide/en/logstash/current/docker-config.html) out for setting up the logstash config. In general, mount the pipeline config `/usr/share/logstash/pipeline/` and the settings config `/usr/share/logstash/pipeline/logstash.conf` OR `/usr/share/logstash/pipeline/logstash.yml`.

[Here's](https://cloudaffaire.com/how-to-create-a-pipeline-in-logstash/) a good explanation of logstash pipelines. Try to create one without any beats first like in [this example](https://rzetterberg.github.io/nginx-elk-logging.html) if you want to understand what's really happening - you'll have to manually send your logs to from NGINX to logstash by mounting the directories. The documentation is pretty confusing, but utilizing these examples with Elastic's [offical docs](https://www.elastic.co/guide/en/logstash/current/dir-layout.html#docker-layout) for where the files should be mounted helps. Definitely super cumbersome and wouldn't recommend if a beat can do the job for you.

#### Filebeat
There's few ways to use beats.

1. Harvest with beat on the stdout/stderr or mounted custom log location -> send to logstash for transformation -> logstash ships to elasticsearch
2. Harvest with beat on the stdout/stderr or mounted custom log location -> use [beat modules](https://www.elastic.co/guide/en/beats/metricbeat/current/metricbeat-modules.html) for transformation -> beat ships to elasticsearch

We did both for learning purposes, but in the future, we're going with the latter because, well, why do more work? We would use autodiscovery hints which are activated by Docker container labels to help trace logs on stdout/stderr.

```yml
labels:
	- "co.elastic.logs/enabled=true"
	- "co.elastic.logs/module=nginx"
```

[This](http://blog.immanuelnoel.com/2019/04/12/a-log-analyzer-with-elk-stack-nginx-and-docker/) guide puts it together pretty well actually.
