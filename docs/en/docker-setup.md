# Docker Setup Guide

This guide explains how to set up automatic Docker image building and publishing for the Telegram Search Bot using GitHub Actions.

## Automatic Building with GitHub Actions

The project includes a GitHub Actions workflow that automatically builds and publishes Docker images to Docker Hub whenever:

1. Code is pushed to the main/master branch
2. A new version tag is created (format: `v*.*.*`)
3. The workflow is manually triggered

### Setting Up GitHub Secrets

To enable automatic building, you need to add the following secrets to your GitHub repository:

1. Go to your GitHub repository
2. Click on "Settings" > "Secrets and variables" > "Actions"
3. Click "New repository secret"
4. Add the following secrets:

   - **DOCKER_HUB_USERNAME**: Your Docker Hub username
   - **DOCKER_HUB_TOKEN**: Your Docker Hub access token (not your password)

### Creating a Docker Hub Access Token

1. Log in to [Docker Hub](https://hub.docker.com/)
2. Click on your username in the top-right corner and select "Account Settings"
3. Go to the "Security" tab
4. Click "New Access Token"
5. Give your token a name (e.g., "GitHub Actions")
6. Select the appropriate permissions (at least "Read & Write")
7. Copy the generated token and save it as the `DOCKER_HUB_TOKEN` secret in GitHub

### Manually Triggering a Build

You can manually trigger a build:

1. Go to the "Actions" tab in your GitHub repository
2. Select the "构建并发布 Docker 镜像" workflow
3. Click "Run workflow"
4. Select the branch to build from
5. Click "Run workflow"

## Using the Docker Image

Once built, you can use the Docker image as follows:

```bash
# Pull the image
docker pull yourusername/telegram-search-bot:latest

# Run the container
docker run -d \
  -v $(pwd)/config:/app/config \
  -e TELEGRAM_BOT_TOKEN=your_token_here \
  yourusername/telegram-search-bot:latest
```

Or with docker-compose:

```yaml
version: "3"
services:
  telegram-search-bot:
    image: yourusername/telegram-search-bot:latest
    volumes:
      - ./config:/app/config
    environment:
      - TELEGRAM_BOT_TOKEN=your_token_here
```

## Available Tags

The following tags are automatically generated:

- `latest`: Always points to the latest build from the main branch
- `YYYYMMDD`: Date-based tag for the main branch (e.g., `20230615`)
- `v1.2.3`: Full version tag (when you create a release tag)
- `1.2`: Major.Minor version tag
- `short-sha`: Short Git commit SHA

## Troubleshooting

If the automatic build fails, check:

1. GitHub Actions logs for detailed error messages
2. Ensure your Docker Hub credentials are correct
3. Verify that your Dockerfile is valid and builds successfully locally
