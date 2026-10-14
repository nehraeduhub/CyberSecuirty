// Renders meshcentral-data/config.json from environment variables.
// Run at container start so the configuration is reproducible and never edited by hand.
'use strict';
const fs = require('fs');

const env = (k, d) => (process.env[k] !== undefined && process.env[k] !== '' ? process.env[k] : d);
const bool = (k, d) => String(env(k, d)).toLowerCase() === 'true';
const int = (k, d) => parseInt(env(k, d), 10);

const host = env('MESH_HOSTNAME');
if (!host) { console.error('MESH_HOSTNAME is required'); process.exit(1); }
const keyFile = env('MESH_LOGIN_KEY_FILE', '/run/secrets/mesh_login_key');
const loginKey = fs.readFileSync(keyFile, 'utf8').replace(/\s+/g, '');
if (!/^[0-9a-fA-F]{160}$/.test(loginKey)) { console.error(keyFile + ' must contain 80 bytes as 160 hex characters'); process.exit(1); }

const trustedProxy = env('MESH_TRUSTED_PROXY', '');
const config = {
  settings: {
    cert: host,
    port: int('MESH_PORT', 4430),           // plain HTTP inside the Docker network; TLS ends at NGINX
    aliasPort: int('MESH_ALIAS_PORT', 443), // port agents and browsers use
    redirPort: 0,
    tlsOffload: trustedProxy ? trustedProxy.split(',').map(s => s.trim()) : true,
    trustedProxy: trustedProxy ? trustedProxy.split(',').map(s => s.trim()) : true,
    WANonly: true,
    exactPorts: true,
    LoginCookieEncryptionKey: loginKey,
    allowLoginToken: true,
    allowFraming: true,
    agentTimeStampServer: false,   // never reach an Internet timestamp server when signing agents
    selfUpdate: false,
    npmPath: '/bin/false',         // never try to install modules at runtime (offline image)
    webRTC: false,                 // all traffic stays on the server relay (TCP 443)
    mpsPort: 0,                    // Intel AMT CIRA (TCP 4433) not used
    AgentPong: int('MESH_AGENT_PONG_SECONDS', 60),
    plugins: { enabled: false },
    maxInvalidLogin: { time: 10, count: 10, coolofftime: 30 }
  },
  domains: {
    '': {
      title: env('MESH_TITLE', 'BSF Remote'),
      title2: env('MESH_TITLE2', 'Remote Console'),
      certUrl: env('MESH_CERT_URL', 'https://' + host + ':443/'),
      newAccounts: false,
      userConsentFlags: int('MESH_DOMAIN_CONSENT_FLAGS', 64), // always show the connection bar to the local user
      userSessionIdleTimeout: int('MESH_IDLE_TIMEOUT_MINUTES', 15),
      clipboardGet: bool('MESH_CLIPBOARD_GET', 'true'),
      clipboardSet: bool('MESH_CLIPBOARD_SET', 'true'),
      geoLocation: false,
      novnc: false,
      mstsc: false,
      ssh: false,
      agentInviteCodes: false,
      lockAgentDownload: false,
      // Only the server console is enabled (used by the portal service account to close technician web sessions).
      myServer: { backup: false, restore: false, upgrade: false, errorlog: false, console: true, trace: false, config: false },
      desktopPrivacyBarText: env('MESH_PRIVACY_BAR_TEXT', 'BSF Remote - authorized support session in progress'),
      agentCustomization: {
        displayName: env('MESH_AGENT_DISPLAY_NAME', 'BSF Remote Support Agent'),
        description: 'BSF Remote internal remote-support agent',
        companyName: env('MESH_AGENT_COMPANY', 'BSF'),
        serviceName: 'BSFRemoteAgent',
        fileName: 'BSFRemoteAgent'
      },
      sessionRecording: {
        filepath: env('MESH_RECORDINGS_PATH', '/opt/meshcentral/meshcentral-recordings'),
        index: true,
        onlySelectedDeviceGroups: true,
        protocols: [1, 2, 5]
      }
    }
  }
};
process.stdout.write(JSON.stringify(config, null, 2) + '\n');
