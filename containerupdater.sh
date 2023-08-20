for file in *-compose.yml
do
    # pull all updated images
    docker compose -f "$file" pull
    # restart containers with latest versions
    docker compose -f "$file" up -d
    # remove images
    docker image prune -f -a
done
