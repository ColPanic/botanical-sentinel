import { fetchNodes } from "$lib/api";
import type { PageServerLoad } from "./$types";

export const load: PageServerLoad = async () => {
  const nodes = await fetchNodes();
  return { nodes };
};
