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
# Pull the latest image
# --------------------
pull_image() {
    log_info "Pulling latest image for service '$SERVICE_NAME'..."
    if docker compose -f "$COMPOSE_FILE" pull "$SERVICE_NAME"; then
        log_success "Image pulled successfully."
    else
        log_error "Failed to pull image for service '$SERVICE_NAME'."
        exit 1
    fi
}

# --------------------
# Stop the service
# --------------------
stop_service() {
    log_info "Stopping service '$SERVICE_NAME'..."
    if docker compose -f "$COMPOSE_FILE" stop "$SERVICE_NAME"; then
        log_success "Service stopped."
    else
        log_error "Failed to stop service '$SERVICE_NAME'."
        exit 1
    fi
}

# --------------------
# Start the service
# --------------------
start_service() {
    log_info "Starting service '$SERVICE_NAME' with the new image..."
    if docker compose -f "$COMPOSE_FILE" up -d --no-deps "$SERVICE_NAME"; then
        log_success "Service '$SERVICE_NAME' started successfully."
    else
        log_error "Failed to start service '$SERVICE_NAME'."
        exit 1
    fi
}

# --------------------
# Remove old images
# --------------------
cleanup_old_images() {
    log_info "Cleaning up dangling images..."
    if docker image prune -f; then
        log_success "Old images removed."
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
    pull_image
    stop_service
    start_service
    cleanup_old_images
    show_status

    echo "=============================================="
    log_success "Update complete for service '$SERVICE_NAME'!"
    echo "=============================================="
}

main
