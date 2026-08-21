# Raspberry Pi CI/CD

Pushes to `main` or `master` run linting and tests, then copy a clean release to the
Raspberry Pi. The Pi builds the ARM-compatible images and starts the application with
Docker Compose. Pull requests run CI only.

## 1. Prepare the Raspberry Pi

Docker Engine with the Compose plugin must be installed, and the deployment user must
be able to run `docker` without `sudo`.

```bash
ssh raspi@112.186.136.153 -p 2222
docker version
docker compose version
mkdir -p "$HOME/keyback/releases" "$HOME/keyback/shared"
```

If Docker requires `sudo`, add the user to the Docker group, then sign out and back in:

```bash
sudo usermod -aG docker raspi
```

## 2. Create a deployment SSH key

Create a dedicated key outside the repository on your workstation. Do not add a
passphrase because GitHub Actions runs non-interactively.

```powershell
$keyPath = "$env:USERPROFILE\.ssh\keyback_github_actions"
ssh-keygen -t ed25519 -C "keyback-github-actions" -f $keyPath -N '""'
Get-Content "$keyPath.pub" | ssh -p 2222 raspi@112.186.136.153 `
  'umask 077; mkdir -p ~/.ssh; cat >> ~/.ssh/authorized_keys'
ssh -i $keyPath -p 2222 raspi@112.186.136.153
```

After confirming that key authentication works, the server password should be changed
because a password shared outside the server must be treated as exposed.

## 3. Configure GitHub

In the repository, open **Settings > Environments**, create an environment named
`production`, then add these environment secrets:

| Secret | Value |
| --- | --- |
| `RASPI_HOST` | `112.186.136.153` |
| `RASPI_PORT` | `2222` |
| `RASPI_USER` | `raspi` |
| `RASPI_SSH_KEY` | Entire contents of `keyback_github_actions` (the private key) |
| `RASPI_KNOWN_HOSTS` | Output of `ssh-keyscan -p 2222 112.186.136.153` |
| `PRODUCTION_ENV_FILE` | Entire production `.env` file, based on `.env.example` |

Protecting the `production` environment with required reviewers is optional. Do not
store the server password, SSH private key, or production `.env` in Git.

## 4. Deploy

Push to `main` or `master`, or run **Actions > CI/CD > Run workflow**. Releases are
stored under `~/keyback/releases/<commit SHA>`, and `~/keyback/current` points to the
last healthy release. The Compose project name is always `keyback`, so the PostgreSQL
volume survives deployments. Each backend image is tagged with its commit SHA; a failed
health check automatically starts the previous healthy image again.

Check the deployment on the Pi with:

```bash
cd "$HOME/keyback/current"
docker compose --project-name keyback ps
docker compose --project-name keyback logs --tail=100 backend
```
