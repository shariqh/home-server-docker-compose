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

Coming Soon

[This](https://github.com/deviantony/docker-elk) helped a lot
[Running the Elastic Stack on Docker](https://www.elastic.co/guide/en/elastic-stack-get-started/current/get-started-docker.html)