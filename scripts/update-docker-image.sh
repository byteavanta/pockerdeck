#!/bin/bash

# =============================================================================
# Docker Compose Image Updater
# Usage: ./update-docker-image.sh [service_name] [compose_file]
# Example: ./update-docker-image.sh myapp docker-compose.yml
# =============================================================================

set -e  # Exit on error

# --------------------
# Configuration
# --------------------
SERVICE_NAME="${1:-}"
COMPOSE_FILE="${2:-docker-compose.yml}"
TIMESTAMP=$(date +"%Y-%m-%d %H:%M:%S")

# --------------------
# Colors for output
# --------------------
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# --------------------
# Helper functions
# --------------------
log_info()    { echo -e "${BLUE}[INFO]${NC}    $1"; }
log_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
log_warning() { echo -e "${YELLOW}[WARNING]${NC} $1"; }
log_error()   { echo -e "${RED}[ERROR]${NC}   $1"; }

# --------------------
# Check dependencies
# --------------------
check_dependencies() {
    log_info "Checking dependencies..."

    if ! command -v docker &>/dev/null; then
        log_error "'docker' is not installed or not in PATH."
        exit 1
    fi

    if ! docker compose version &>/dev/null; then
        log_error "'docker compose' plugin is not available. Please install Docker Compose v2."
        exit 1
    fi

    log_success "All dependencies are available."
}

# --------------------
# Validate inputs
# --------------------
validate_inputs() {
    if [[ -z "$SERVICE_NAME" ]]; then
        log_error "No service name provided."
        echo "Usage: $0 [service_name] [compose_file]"
        exit 1
    fi

    if [[ ! -f "$COMPOSE_FILE" ]]; then
        log_error "Compose file '$COMPOSE_FILE' not found."
        exit 1
    fi

    log_info "Service:      $SERVICE_NAME"
    log_info "Compose file: $COMPOSE_FILE"
}

# --------------------
# Get the image name for the service from the compose file
# --------------------
get_service_image() {
    docker compose -f "$COMPOSE_FILE" config --format json 2>/dev/null \
        | grep -o "\"image\":\"[^\"]*\"" \
        | head -1 \
        | sed 's/"image":"//;s/"//' || echo ""
}

# --------------------
# Stop the service and remove the container
# --------------------
stop_and_remove_container() {
    log_info "Stopping service '$SERVICE_NAME'..."
    docker compose -f "$COMPOSE_FILE" stop "$SERVICE_NAME" 2>/dev/null || true
    log_success "Service stopped."

    log_info "Removing container for service '$SERVICE_NAME'..."
    docker compose -f "$COMPOSE_FILE" rm -f "$SERVICE_NAME" 2>/dev/null || true
    log_success "Container removed."
}

# --------------------
# Delete only the :latest tagged image to force a fresh pull
# --------------------
delete_old_image() {
    log_info "Resolving image for service '$SERVICE_NAME'..."

    # Get the image name from docker compose config
    IMAGE_NAME=$(get_service_image)

    # Fallback: try to get the image from currently running/stopped containers
    if [[ -z "$IMAGE_NAME" ]]; then
        IMAGE_NAME=$(docker compose -f "$COMPOSE_FILE" images "$SERVICE_NAME" --format "{{.Repository}}:{{.Tag}}" 2>/dev/null | head -1)
    fi

    if [[ -n "$IMAGE_NAME" && "$IMAGE_NAME" != ":" ]]; then
        # Strip any existing tag and force :latest
        IMAGE_BASE="${IMAGE_NAME%%:*}"
        LATEST_IMAGE="${IMAGE_BASE}:latest"

        log_info "Deleting latest image: $LATEST_IMAGE"
        if docker rmi -f "$LATEST_IMAGE" 2>/dev/null; then
            log_success "Image '$LATEST_IMAGE' deleted."
        else
            log_warning "Could not delete image '$LATEST_IMAGE' (may not exist locally yet)."
        fi
    else
        log_warning "Could not determine image name for service '$SERVICE_NAME'. Skipping image deletion."
    fi
}

# --------------------
# Pull a completely fresh image
# --------------------
pull_image() {
    log_info "Pulling fresh image for service '$SERVICE_NAME'..."
    if docker compose -f "$COMPOSE_FILE" pull "$SERVICE_NAME"; then
        log_success "Fresh image pulled successfully."
    else
        log_error "Failed to pull image for service '$SERVICE_NAME'."
        exit 1
    fi
}

# --------------------
# Start the service with the new image
# --------------------
start_service() {
    log_info "Starting service '$SERVICE_NAME' with the new image..."
    if docker compose -f "$COMPOSE_FILE" up -d --no-deps --force-recreate "$SERVICE_NAME"; then
        log_success "Service '$SERVICE_NAME' started successfully with the new image."
    else
        log_error "Failed to start service '$SERVICE_NAME'."
        exit 1
    fi
}

# --------------------
# Remove dangling images
# --------------------
cleanup_old_images() {
    log_info "Cleaning up dangling images..."
    if docker image prune -f; then
        log_success "Dangling images removed."
    else
        log_warning "Image cleanup failed (non-critical)."
    fi
}

# --------------------
# Show running container
# --------------------
show_status() {
    log_info "Current status of '$SERVICE_NAME':"
    docker compose -f "$COMPOSE_FILE" ps "$SERVICE_NAME"
}

# --------------------
# Main
# --------------------
main() {
    echo "=============================================="
    echo " Docker Compose Image Updater"
    echo " $TIMESTAMP"
    echo "=============================================="

    check_dependencies
    validate_inputs
    stop_and_remove_container
    delete_old_image
    pull_image
    start_service
    cleanup_old_images
    show_status

    echo "=============================================="
    log_success "Update complete for service '$SERVICE_NAME'!"
    echo "=============================================="
}

main