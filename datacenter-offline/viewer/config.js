// DC Viewer settings. install-offline.sh rewrites glpiUrl from GLPI_PORT in .env.
window.DC_VIEWER_CONFIG = {
  // Where "Open in GLPI" links point. Empty = same host as this page, port 80.
  glpiUrl: '',
  // REST API path, proxied by the portal container on the same origin.
  apiUrl: '../apirest.php',
  // Optional App-Token if you set one on the GLPI API client.
  appToken: '',
  // Auto refresh interval
  refreshMinutes: 5
};
