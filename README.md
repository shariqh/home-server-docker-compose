# Getting Started

Each docker-compose will have its own section below to help with getting started as needed.

---

1. In general you'll need to add your environment variables either in the shell or in your `/etc/environment` file and source it or restart your box. Otherwise you can always hardcode them in the docker-compose files.

Sample `/etc/environement`
```
PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:/usr/games:/usr/local/games:/snap/bin"

# user added variables
export TZ='America/Chicago'
export DUCKDNS_URL='shariq-dev.duckdns.org'
export DUCKDNS_TOKEN='{enter your token here}'
export ELASTICSEARCH_USERNAME='elastic'
export ELASTICSEARCH_PASSWORD='MagicPassword'
```

Sourcing from an updated file
```
source /etc/environment
```

2. Now you can clone down the repository with HTTPS or SSH if you've set up your key

Cloning with SSH
```
git clone https://github.com/shariqh/home-server-docker-compose.git
```

3. Navigate to your newly cloned repo and run `docker-compose up -d` to run the file names `docker-compose.yml`. You'll need to specify the filename otherwise

Running a specific docker-compose file
```
docker-compose -f media-compose.yml up -d
```

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

### Authelia

Coming soon, maybe... 2FA with https://github.com/authelia/authelia

## media-compose.yml

Coming Soon

[Plex](plex.tv)
Here;s the documentation: https://hub.docker.com/r/linuxserver/plex
This is important: https://docs.docker.com/network/host/


[Tautulli](https://github.com/Tautulli/Tautulli)

## elk-compose.yml

In Progress...

[This](https://github.com/deviantony/docker-elk) helped a lot

[Running the Elastic Stack on Docker](https://www.elastic.co/guide/en/elastic-stack-get-started/current/get-started-docker.html)

#### Logstash
Check [this](https://www.elastic.co/guide/en/logstash/current/docker-config.html) out for setting up the logstash config. In general, mount the pipeline config `/usr/share/logstash/pipeline/` and the settings config `/usr/share/logstash/pipeline/logstash.conf` OR `/usr/share/logstash/pipeline/logstash.yml`.

[Here's](https://cloudaffaire.com/how-to-create-a-pipeline-in-logstash/) a good explanation of logstash pipelines. Try to create one without any beats first like in [this example](https://rzetterberg.github.io/nginx-elk-logging.html) if you want to understand what's really happening - you'll have to manually send your logs to from NGINX to logstash by mounting the directories. The documentation is pretty confusing, but utilizing these examples with Elastic's [offical docs](https://www.elastic.co/guide/en/logstash/current/dir-layout.html#docker-layout) for where the files should be mounted helps. Definitely super cumbersome and wouldn't recommend if a beat can do the job for you.

#### Filebeat
TL;DR There's few ways to use beats. I haven't gotten any of them working so maybe skip this section for now?

1. Harvest with beat on the stdout/stderr or mounted custom log location -> send to logstash for transformation -> logstash ships to elasticsearch
2. Harvest with beat on the stdout/stderr or mounted custom log location -> use [beat modules](https://www.elastic.co/guide/en/beats/metricbeat/current/metricbeat-modules.html) for transformation -> beat ships to elasticsearch

We did both for learning purposes, but in the future, we're going with the latter because, well, why do more work? We would use autodiscovery hints which are activated by Docker container labels to help trace logs on stdout/stderr.

```yml
labels:
	- "co.elastic.logs/enabled=true"
	- "co.elastic.logs/module=nginx"
```

[This](http://blog.immanuelnoel.com/2019/04/12/a-log-analyzer-with-elk-stack-nginx-and-docker/) guide puts it together pretty well actually.

#### Curator
Using [Curator](https://hub.docker.com/r/bitnami/elasticsearch-curator/) to help auto remove logs that are old (cause why would I want them, right?)