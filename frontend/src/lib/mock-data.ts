// Mock data for Sprint 2. Replaced by real backend/WP data in later sprints
// (projects come from Postgres; plans come from the LangGraph orchestrator).

import type { Plan, Project } from "@/lib/types";

export const MOCK_PROJECTS: Project[] = [
  {
    id: "proj-acme",
    name: "Acme Photography",
    url: "https://acme-photo.example",
    status: "active",
    pages: 6,
  },
  {
    id: "proj-bistro",
    name: "Riverside Bistro",
    url: "https://riverside.example",
    status: "active",
    pages: 4,
  },
  {
    id: "proj-launch",
    name: "Launchpad SaaS",
    url: "https://launchpad.example",
    status: "draft",
    pages: 1,
  },
];

/**
 * Build a plausible plan from a free-text request. This stands in for the
 * orchestrator's planning step; it just keys off a few words so the demo
 * feels responsive.
 */
export function buildMockPlan(request: string): Plan {
  const lower = request.toLowerCase();
  const wantsContact = /contact|form|email/.test(lower);
  const wantsSeo = /seo|meta|rank|search/.test(lower);

  const steps: Plan["steps"] = [
    {
      id: "step-theme",
      title: "Apply theme & global styles",
      description:
        "Set the color palette, typography, and Elementor global settings to match the requested aesthetic.",
      tool: "wp.applyTheme",
      channel: "REST API",
      diff: "+ palette: dark / minimal\n+ heading font: Inter\n+ body font: Inter",
    },
    {
      id: "step-home",
      title: "Build the home page",
      description:
        "Generate a hero, feature grid, and footer as Elementor sections, then write _elementor_data.",
      tool: "wp.createPage",
      channel: "REST API",
      diff: '+ page "Home" (hero, features, footer)\n+ _elementor_data: 3 sections',
    },
  ];

  if (wantsContact) {
    steps.push({
      id: "step-contact",
      title: "Add a contact page with a form",
      description:
        "Install a forms plugin, then build a contact page wired to the form.",
      tool: "wp.installPlugin + wp.createPage",
      channel: "WP-CLI",
      diff: "+ plugin: contact-form-7 (install + activate)\n+ page \"Contact\" with form block",
    });
  }

  if (wantsSeo) {
    steps.push({
      id: "step-seo",
      title: "Configure SEO metadata",
      description:
        "Generate meta titles/descriptions and schema markup via the SEO plugin's REST endpoints.",
      tool: "wp.configureSeo",
      channel: "REST API",
      diff: "+ meta titles + descriptions for all pages\n+ Organization schema markup",
    });
  }

  steps.push({
    id: "step-flush",
    title: "Regenerate Elementor CSS",
    description:
      "Run `wp elementor flush-css` so the new layouts render correctly.",
    tool: "wp.flushCss",
    channel: "WP-CLI",
    diff: "$ wp elementor flush-css",
  });

  return {
    summary: `Plan to handle: “${request.trim()}”. ${steps.length} steps, all behind the approval gate before any write.`,
    steps,
  };
}
