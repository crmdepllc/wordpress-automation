<?php
/**
 * Plugin Name: WPA Companion
 * Description: Registers the protected post meta this automation platform writes
 * (Elementor layout data, Yoast/RankMath SEO fields, our JSON-LD meta) with
 * show_in_rest, so WordPress core stops silently dropping REST writes to it.
 * Must-use plugin: auto-loaded, no activation step, cannot be left deactivated.
 * Version: 1.0.0
 */

if (!defined('ABSPATH')) {
    exit;
}

add_action('init', function () {
    // The exact set of protected meta keys the codebase writes today — an
    // explicit allowlist, not a wildcard show_in_rest registration.
    $meta_keys = [
        // Elementor layout (backend/app/wp/rest_client.py: create_elementor_page)
        '_elementor_data',
        '_elementor_edit_mode',
        '_elementor_template_type',
        // Yoast SEO (backend/app/agent/skills/seo/providers.py)
        '_yoast_wpseo_title',
        '_yoast_wpseo_metadesc',
        // RankMath SEO (backend/app/agent/skills/seo/providers.py)
        'rank_math_title',
        'rank_math_description',
        // This platform's JSON-LD meta (backend/app/agent/skills/seo/skill.py)
        '_seo_schema_jsonld',
    ];

    $auth_callback = function ($allowed, $meta_key, $post_id) {
        return current_user_can('edit_post', $post_id);
    };

    foreach (['post', 'page'] as $post_type) {
        foreach ($meta_keys as $meta_key) {
            register_post_meta($post_type, $meta_key, [
                'show_in_rest'  => true,
                'single'        => true,
                'type'          => 'string',
                'auth_callback' => $auth_callback,
            ]);
        }
    }
});
