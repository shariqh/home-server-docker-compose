for file in *-compose.yml
do
    # pull all updated images
    docker-compose -f "$file" pull
    # remove all old images
    docker-compose -f "$file" up -d
done