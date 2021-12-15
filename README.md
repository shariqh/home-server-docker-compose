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

P.S. use the `containerupdater.sh` to automatically keep your images up to date. Schedule a cronjob for ease of use

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

Since my WiFi router does not support Dynamic DNS, I use [DuckDNS](https://www.duckdns.org/) to bind my public IP to a DuckDNS DNS and then use the [DuckDNS Docker image](https://hub.docker.com/r/linuxserver/duckdns/) to update my public DNS to DuckDNS every five minutes.

### Authelia

Coming soon, maybe... 2FA with https://github.com/authelia/authelia

## media-compose.yml

Coming Soon

[Plex](plex.tv)
Here's the documentation: https://hub.docker.com/r/linuxserver/plex
This is important: https://docs.docker.com/network/host/

[Transmission + OpenVPN]https://github.com/haugene/docker-transmission-openvpn)
And docs: https://haugene.github.io/docker-transmission-openvpn/run-container/

[Tautulli](https://github.com/Tautulli/Tautulli)

## op-compose.yml

Used to set up 1Password Secrets Automation. First, you'll need to follow [this guide](https://www.bundleapps.io/blog/storing-and-accessing-environment-variables-in-1password) and manually copy the `1password-credentials.json` over. 

