for file in *-compose.yml
do
    # pull all updated images
    docker-compose -f "$file" pull
done