# Install and test P95 Explorer

Choose your platform: **[Windows](#windows)** · **[macOS](#macos)** · **[Linux](#linux)**.

The steps below build and run the application from the public source repository. No prebuilt image needs to be pulled from a P95 Explorer registry. You do not need Python, Node.js, a GitHub login, or a Cato API key for the demo. Use a current browser. The first build needs internet access to download the Python base image; later demo use works locally.

Docker's current operating-system, virtualization and hardware requirements are listed in its installation pages linked below. Choose the Docker installer for your processor. P95 Explorer builds Linux images for AMD64 (Intel/AMD) and ARM64 (including Apple silicon); Windows hosts must run Linux containers.

## Windows

Use **PowerShell** for these commands. The project does not require running commands inside a WSL terminal.

1. Install [Docker Desktop for Windows](https://docs.docker.com/desktop/setup/install/windows-install/). Use the WSL 2 backend and follow Docker's prerequisites, including enabling virtualization where required. Complete any requested Windows restart.
2. Open **Docker Desktop** from the Start menu and wait for the engine to be running. Use **Linux containers**. If the Docker menu offers “Switch to Linux containers,” select it. If it offers “Switch to Windows containers,” you are already in the right mode. Menu availability depends on the installation mode.
3. Open a new PowerShell window and check Docker:

   ```powershell
   docker version
   docker compose version
   ```

   `docker version` should show both **Client** and **Server** information. If the Server section fails, Docker Desktop is not ready yet.

4. If Git is available (`git --version`), choose a writable project folder and run:

   ```powershell
   git clone https://github.com/dzcassell/p95explorer.git
   cd p95explorer
   docker compose up --build -d
   ```

   **Without Git:** open [the GitHub repository](https://github.com/dzcassell/p95explorer), select **Code → Download ZIP**, and extract the ZIP. In PowerShell, change to the extracted directory that contains `compose.yaml`, then run:

   ```powershell
   # Replace this example with the actual extracted folder.
   cd "$env:USERPROFILE\Downloads\p95explorer-main"
   docker compose up --build -d
   ```

5. Open **[http://localhost:8080](http://localhost:8080)** in your browser, then continue with [verification](#verify-your-installation).

Docker Desktop supports specific Windows desktop versions. Windows Server installations need a separately configured Linux container host; this guide does not assume Docker Desktop is available there. See Docker's linked platform requirements for Windows on ARM availability.

## macOS

Use **Terminal** for these commands.

1. Install [Docker Desktop for Mac](https://docs.docker.com/desktop/setup/install/mac-install/). Select **Apple silicon** for an M-series Mac or **Intel** for an Intel Mac. You can find the processor under **Apple menu → About This Mac**.
2. Open **Docker** from Applications and complete its initial setup. Wait for the engine to be running. Keep Docker Desktop running while you use P95 Explorer.
3. Open Terminal and verify:

   ```sh
   docker version
   docker compose version
   ```

   Expect both **Client** and **Server** information from the first command.

4. If Git is available (`git --version`), choose a writable project folder and run:

   ```sh
   git clone https://github.com/dzcassell/p95explorer.git
   cd p95explorer
   docker compose up --build -d
   ```

   **Without Git:** use **Code → Download ZIP** on [GitHub](https://github.com/dzcassell/p95explorer), unzip it, and run these commands from the extracted folder. Adjust the path if you saved it elsewhere:

   ```sh
   cd "$HOME/Downloads/p95explorer-main"
   docker compose up --build -d
   ```

5. Open **[http://localhost:8080](http://localhost:8080)** and continue with [verification](#verify-your-installation).

You do not need Homebrew, a separate Python installation, or Rosetta specifically for this app's native ARM64 image.

## Linux

Use your distribution's terminal. Docker Engine with the Compose plugin is sufficient; Docker Desktop is optional.

1. Follow the official [Docker Engine installation instructions for your distribution](https://docs.docker.com/engine/install/). Install the **Docker Compose plugin** and **Buildx plugin** along with Engine/CLI; the distribution-specific Docker repository instructions list the appropriate packages. If Engine is already installed but Compose is missing, follow [Docker's Compose plugin guide](https://docs.docker.com/compose/install/linux/).
2. Start Docker's service using your distribution's service manager. On a systemd machine:

   ```sh
   sudo systemctl start docker
   ```

3. Check the installation:

   ```sh
   docker version
   docker compose version
   ```

   If access to the Docker socket is denied, use `sudo docker version` and `sudo docker compose version`. You can then prefix the Docker commands in this guide with `sudo`. For a non-root setup, follow [Docker's post-installation instructions](https://docs.docker.com/engine/install/linux-postinstall/); Docker group membership grants substantial host access. Keep using the same Docker context throughout setup and testing.

4. With Git available, choose a writable project folder and run:

   ```sh
   git clone https://github.com/dzcassell/p95explorer.git
   cd p95explorer
   docker compose up --build -d
   ```

   If you need elevated Docker access, the last command becomes `sudo docker compose up --build -d`; Git itself does not need `sudo`.

   **Without Git:** download and extract **Code → Download ZIP** from [GitHub](https://github.com/dzcassell/p95explorer). Open a terminal in the extracted directory containing `compose.yaml`, then run `docker compose up --build -d` (with `sudo` if required).

5. On a Linux desktop, open **[http://localhost:8080](http://localhost:8080)**. On a headless Linux host, run the application there and forward the port from your browser machine:

   ```sh
   # Run this on the machine with your browser, substituting the SSH destination.
   ssh -N -L 18080:127.0.0.1:8080 your-user@your-linux-host
   ```

   Keep that SSH session open, then browse to **http://localhost:18080** on your browser machine. The app's Compose configuration keeps the service bound to loopback on the Linux host.

## Verify your installation

Run all Compose commands from the repository/extracted folder containing `compose.yaml`.

```sh
docker compose ps
docker compose logs --tail=50 explorer
```

The `explorer` service should be **Up**, then **healthy** after its health check runs. The startup log should include `P95 Explorer listening on 0.0.0.0:8080`. That is the address inside the container; the host mapping remains local-only.

Open **http://localhost:8080/api/health** in your browser. Expected response:

```json
{"status": "ok"}
```

Then open **http://localhost:8080** and try this checklist on each machine:

- Select **Load demo**. Expect six synthetic sites, three regional summaries, and 100% month coverage.
- Change the license model between bursting, fixed site, and enforced pool. Capacity recommendations should change.
- Increase **Projected growth**. Modeled demand should increase.
- Edit a regional pool capacity and a site allocation. Review the resulting capacity pressure.
- Move the P95 lesson's burst duration from **70** to **75 minutes**. The illustrated daily P95 should change from **50** to **200 Mbps**.
- Choose **Save scenario & site mapping**, refresh the page, and check that your scenario remains selected.
- Export a CSV. Optional: import it to test the separate imported-data workspace.

Synthetic demo data makes it possible to test installation and calculations before connecting a real tenant. The selected observation month is a complete prior month on a fresh demo workspace.

## Optional Cato credentials

The simplest first connection is **Connect tenant** in the browser. Enter a read-only API key, tenant/account ID and correct endpoint. The application does not save the entered key. No `.env` file is required for this route.

For credentials supplied through Docker, create `.env` in the same folder as `compose.yaml`.

**Windows PowerShell:**

```powershell
Copy-Item .env.example .env
notepad .env
```

**macOS / Linux:**

```sh
cp .env.example .env
```

Open `.env` in your preferred text editor, fill in the values, save it, and recreate the service:

```sh
docker compose up -d --force-recreate
```

Use `CATO_ACCOUNT_ID`, `CATO_API_KEY` and `CATO_API_ENDPOINT` as shown in `.env.example`. In the connection dialog, leave the account ID and key blank to use the environment values, and set the endpoint to match your configured Cato API host. `.env` is excluded from Git and the Docker image; it still contains your key locally, so do not share it with a test report.

Follow [Connect to Cato in the README](../README.md#connect-to-cato) for site selection and verified license region mapping. A tenant key is not necessary for cross-platform demo testing.

## Stop and start again

```sh
# Stop and remove the container, retaining the named data volume.
docker compose down

# Start again using the image already built on this machine.
docker compose up -d
```

Keep the same project folder/name to reuse the same Compose data volume. Changing the folder name can select a different Compose project and therefore a different data volume. Docker Desktop must be running on Windows/macOS.

**Do not run `docker compose down -v` or `docker compose down --volumes` unless you intend to delete stored observations and scenarios.**

## Update to the latest version

For a Git clone, run these commands from the original project folder:

```sh
git pull --ff-only
docker compose up --build -d
docker compose ps
```

Wait for any Cato collection to finish before updating; restarting the container interrupts its in-memory job. The named volume retains data. If Git reports local changes, review them before replacing files.

For a ZIP installation, download the latest ZIP and replace the source files in your existing project directory while preserving `.env`. Keep that directory's name the same, then run `docker compose up --build -d`. Data is in Docker's named volume, not the extracted source folder. Refresh the browser after an update to load the latest UI.

## Testing on another machine

Each machine keeps its own Docker image, SQLite history and saved scenario. Signing into GitHub or cloning the same repository does not synchronize usage data or credentials.

For a fresh platform test, install and **Load demo** on each machine. To carry observed usage between machines, use **Export CSV** on the source machine and **Import CSV** on the destination. CSV transfers the selected month's observations and saved site regions; it does **not** transfer saved scenario controls, allocations, credentials or the entire history. Re-enter those settings or recollect from Cato as needed. Verify region mapping after import.

For a complete workspace backup, preserve the Compose data volume using [Docker's volume backup/restore guidance](https://docs.docker.com/engine/storage/volumes/#back-up-restore-or-migrate-data-volumes). Stop collection and the application before backing up SQLite files; preserve the entire data directory rather than copying only a potentially active database file.

## Troubleshooting

| Symptom | What to do |
|---|---|
| `docker` is not recognized / command not found | Install Docker, then open a new terminal. On Windows/macOS, start Docker Desktop. |
| Cannot connect to the Docker daemon | Wait for Docker Desktop's engine, or start Docker Engine on Linux. Check `docker version` for a working Server section. |
| `docker: 'compose' is not a docker command` | Update Docker Desktop or install the Linux Compose plugin. Use **`docker compose`**, with a space, throughout this guide. |
| Linux Docker socket permission denied | Use `sudo docker ...` consistently or follow the linked Docker post-installation instructions. |
| Windows reports that WSL or virtualization is unavailable | Complete the prerequisites in Docker's Windows installation guide and restart if required. |
| Windows reports no matching image / container OS mismatch | Confirm Docker is running **Linux containers** and that its installer matches the host processor. |
| Port 8080 is already allocated | Use the alternative host port described below, or stop the other app using 8080. |
| Browser cannot connect | Check `docker compose ps` and logs. Open the URL on the same machine, or use the SSH tunnel for a remote host. |
| `no configuration file provided` | Change to the folder containing `compose.yaml` before running Compose. |
| Build cannot download the Python base image | Check internet connectivity and Docker's proxy settings. First build needs Docker registry access. |
| Workspace appears empty after moving/renaming a folder | Compose project names select separate volumes. Return to the original project folder/name to reuse its volume. |
| Cato connection fails | Verify account ID, read-only permissions, endpoint and any API-key source-IP restrictions. See the README's Cato instructions. |

### If port 8080 is in use

In `compose.yaml`, change only the **host-side** port mapping:

```yaml
ports:
  - "127.0.0.1:18080:8080"
```

Then run `docker compose up -d` and open **http://localhost:18080**. Leave the final `8080` unchanged; it is the port inside the container. Keep the `127.0.0.1` binding for this local deployment.

### Reporting a test issue

Create an [issue on GitHub](https://github.com/dzcassell/p95explorer/issues) with your OS/version, CPU architecture, browser, Docker/Compose versions, the failing step and the error message. Include whether you tested demo or live Cato data. `docker compose ps` and `docker compose logs --tail=50 explorer` are useful diagnostics. Remove tenant-identifying details before sharing; do not include `.env`, API keys or tenant CSV exports.
