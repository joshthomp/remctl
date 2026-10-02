import { build } from 'esbuild';
import {readFile, writeFile} from 'node:fs/promises';
import {createHash} from 'node:crypto';
const result = await build({entryPoints:['src/main.tsx'],bundle:true,write:false,minify:true,format:'iife',target:'es2022',loader:{'.png':'dataurl','.svg':'dataurl'},outdir:'dist'});
const script=result.outputFiles.find(f=>f.path.endsWith('.js')).text.replaceAll('</script','<\\/script');
const css=result.outputFiles.find(f=>f.path.endsWith('.css'))?.text || '';
const html = `<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>RemCTL</title><style>${css}</style></head><body><div id="root"></div><script>${script}</script></body></html>`;
await writeFile('../remctl_workspace.html', html);
// Changing the connection fingerprint makes desktop hosts retire cached server code.
const fingerprint = createHash('sha256').update(html);
for (const name of ['remctl_events.py', 'remctl_plugin.py', 'remctl_workspace.py', 'remctl_mcp.py', 'remctl']) fingerprint.update(await readFile(`../${name}`));
const configPath = '../plugins/remctl/mcp.json';
const config = JSON.parse(await readFile(configPath, 'utf8'));
config.mcpServers.remctl.env.REMCTL_PLUGIN_BUILD = fingerprint.digest('hex').slice(0, 16);
await writeFile(configPath, JSON.stringify(config, null, 2) + '\n');
