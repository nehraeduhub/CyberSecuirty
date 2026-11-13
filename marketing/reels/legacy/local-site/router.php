<?php
$root = getenv('DOCROOT'); $p = parse_url($_SERVER['REQUEST_URI'], PHP_URL_PATH);
if (preg_match('#^/api/(data|books|ctf-data)#', $p)) { http_response_code(403); exit; }
if ($p !== '/' && file_exists($root.$p) && !is_dir($root.$p)) {
  if (str_ends_with($p, '.php')) { chdir(dirname($root.$p)); require $root.$p; return true; }
  return false;
}
readfile($root.'/index.html');
