/// Glyphs of the usage page (textgate: headers, tabs and legends are icons
/// with a screen-reader label, never words), and the chart palette.
library;

import 'package:design_system/design_system.dart';
import 'package:flutter/material.dart';
import 'package:todo_implementer/model/usage/columns.dart';
import 'package:todo_implementer/model/usage/route.dart';
import 'package:todo_implementer/ui/usage/blocks.dart';

/// Tab glyph and screen-reader name per view.
const viewGlyphs = <UsageView, (IconData, String)>{
  UsageView.overview: (Icons.payments_outlined, 'Spend'),
  UsageView.sessions: (Icons.terminal, 'Sessions'),
  UsageView.items: (Icons.checklist, 'Per todo item'),
  UsageView.efficiency: (Icons.speed, 'Efficiency'),
  UsageView.autonomy: (Icons.smart_toy_outlined, 'Autonomy'),
  UsageView.levers: (Icons.tune, 'Levers'),
  UsageView.context: (Icons.description_outlined, 'Context files'),
  UsageView.anomalies: (Icons.warning_amber, 'Anomalies'),
  UsageView.ab: (Icons.compare_arrows, 'A/B'),
  UsageView.more: (Icons.more_horiz, 'More panels'),
  UsageView.session: (Icons.terminal, 'Session'),
  UsageView.file: (Icons.description_outlined, 'Context file'),
  UsageView.panel: (Icons.table_chart_outlined, 'Panel'),
};

/// Header glyph per row key; [kindGlyph] covers the rest.
const keyGlyphs = <String, IconData>{
  'actual': Icons.check,
  'active_s': Icons.timer_outlined,
  'agent_type': Icons.category_outlined,
  'baseline': Icons.horizontal_rule,
  'breaches': Icons.report_outlined,
  'budgets': Icons.account_balance_wallet_outlined,
  'bytes': Icons.data_usage,
  'calls': Icons.call_made,
  'carry_usd': Icons.move_down,
  'category': Icons.category_outlined,
  'cost_usd': Icons.attach_money,
  'cwd': Icons.folder_outlined,
  'date': Icons.event,
  'day': Icons.calendar_today,
  'depth': Icons.layers_outlined,
  'description': Icons.assignment_outlined,
  'detail': Icons.notes,
  'difference': Icons.difference_outlined,
  'final_tag': Icons.flag_outlined,
  'hard': Icons.block,
  'history': Icons.history,
  'home_share': Icons.home_outlined,
  'idx': Icons.tag,
  'item': Icons.checklist,
  'kind': Icons.category_outlined,
  'last_ts': Icons.schedule,
  'lever': Icons.tune,
  'limit': Icons.vertical_align_top,
  'lines': Icons.format_list_numbered,
  'measure': Icons.straighten,
  'median_usd': Icons.align_vertical_center,
  'metric': Icons.straighten,
  'model': Icons.memory,
  'models': Icons.memory,
  'name': Icons.build_outlined,
  'opus': Icons.auto_awesome,
  'opus_share': Icons.auto_awesome,
  'outcome': Icons.verified_outlined,
  'over_share': Icons.trending_up,
  'path': Icons.description_outlined,
  'predicted': Icons.online_prediction,
  'prompts': Icons.chat_bubble_outline,
  'ratio': Icons.functions,
  'repeats': Icons.repeat,
  'repo': Icons.source_outlined,
  'result_tokens': Icons.output,
  'sessions': Icons.terminal,
  'sonnet': Icons.bolt,
  'source': Icons.link,
  'stage': Icons.stairs_outlined,
  'standing': Icons.download_done,
  'status': Icons.traffic_outlined,
  'sub_share': Icons.smart_toy_outlined,
  'subagents': Icons.hub_outlined,
  'target': Icons.gps_fixed,
  'text': Icons.chat_bubble_outline,
  'title': Icons.title,
  'tokens': Icons.token_outlined,
  'ts': Icons.schedule,
  'usd': Icons.attach_money,
  'usd_main': Icons.person_outline,
  'usd_own': Icons.person_outline,
  'usd_per_call': Icons.price_change_outlined,
  'usd_per_day': Icons.today,
  'usd_sub': Icons.smart_toy_outlined,
  'value': Icons.numbers,
  'wall_s': Icons.hourglass_bottom,
  'why': Icons.help_outline,
};

/// The glyph of a column with no entry in [keyGlyphs].
IconData kindGlyph(UsageColumn c) => switch (c.fmt) {
  Fmt.money => Icons.attach_money,
  Fmt.pct => Icons.percent,
  Fmt.secs => Icons.timer_outlined,
  Fmt.big => Icons.data_usage,
  Fmt.when => Icons.schedule,
  Fmt.plain when c.kind == ColKind.number => Icons.numbers,
  Fmt.plain when c.kind == ColKind.tag => Icons.label_outline,
  Fmt.plain => Icons.notes,
};

/// A column's header glyph.
IconData columnGlyph(UsageColumn c) => keyGlyphs[c.key] ?? kindGlyph(c);

/// Shape and colour of a level (never colour alone).
(IconData, Color, String) levelGlyph(Level level) => switch (level) {
  Level.green => (Icons.check_circle_outline, AppPalette.success, 'on target'),
  Level.grey => (
    Icons.radio_button_unchecked,
    AppPalette.mutedOnDark,
    'no data',
  ),
  Level.red => (Icons.warning_amber, AppPalette.danger, 'off target'),
};

/// The validated categorical ramp (`web_ui/src/tokens.css` `--cat-*`), in
/// the usage page's fixed order: cat-2, cat-3, cat-5, cat-4, cat-1.
const seriesColors = <Color>[
  Color(0xFF398FC0),
  Color(0xFFC85A32),
  Color(0xFF8D58BB),
  Color(0xFF228736),
  Color(0xFFC57293),
];

/// The colour of categorical slot [i]; slots past the ramp reuse the last
/// (views never draw more than five series).
Color seriesColor(int i) => seriesColors[i.clamp(0, seriesColors.length - 1)];
