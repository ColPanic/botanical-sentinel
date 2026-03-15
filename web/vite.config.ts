import { sveltekit } from '@sveltejs/kit/vite';
import tailwindcss from '@tailwindcss/vite';
import { defineConfig } from 'vite';

export default defineConfig({
	plugins: [tailwindcss(), sveltekit()],
	server: {
		// Allow access by IP as well as hostname (needed when accessing from LAN by IP)
		allowedHosts: true,
		proxy: {
			'/live': { target: 'ws://localhost:8000', ws: true },
			// Proxy REST API routes so the browser can use relative URLs
			// when PUBLIC_API_URL is not set (see src/lib/api.ts).
			// bypass: pass SvelteKit-internal __data.json requests back to the
			// dev server instead of forwarding them to FastAPI.
			'/nodes': { target: 'http://localhost:8000', bypass: (req) => req.url?.includes('__data') ? req.url : undefined },
			'/devices': { target: 'http://localhost:8000', bypass: (req) => req.url?.includes('__data') ? req.url : undefined },
			'/scan': { target: 'http://localhost:8000', bypass: (req) => req.url?.includes('__data') ? req.url : undefined },
			'/positions': 'http://localhost:8000',
			'/health': 'http://localhost:8000',
		},
	},
});
