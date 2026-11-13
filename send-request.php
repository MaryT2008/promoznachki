<?php
// Обработчик формы заявки: письмо в отдел продаж и подтверждение клиенту.
// Письма уходят с sales@promoznachki.ru через почту хостинга (SPF и DKIM домена).
declare(strict_types=1);

date_default_timezone_set('Europe/Moscow');
header('Content-Type: application/json; charset=utf-8');
header('X-Robots-Tag: noindex, nofollow');
header('Cache-Control: no-store');

const MAIL_TO = 'sales@promoznachki.ru';
const MAIL_FROM = 'sales@promoznachki.ru';
const FROM_NAME = 'ПромоЗначки';
const SUBJECT_SALES = 'Новый запрос с сайта promoznachki.ru';
const SUBJECT_CLIENT = 'Ваша заявка принята — ПромоЗначки';

const MAX_FILES = 5;
const MAX_TOTAL = 10 * 1024 * 1024;
const ALLOWED = ['jpg', 'jpeg', 'png', 'gif', 'webp', 'heic', 'tif', 'tiff', 'bmp', 'svg', 'pdf', 'ai', 'eps', 'cdr', 'psd', 'doc', 'docx', 'rtf', 'odt', 'txt', 'xls', 'xlsx'];
const STOP_WORDS = ['casino', 'crypto', 'bitcoin', 'viagra', 'loan', 'backlinks', 'porn', 'казино', 'ставки', 'займ', 'продвижение сайта'];

// Не больше 5 заявок с одного IP за 10 минут
const RATE_LIMIT = 5;
const RATE_WINDOW = 600;

function reply(int $code, bool $ok, string $message = ''): void
{
    http_response_code($code);
    echo json_encode(['success' => $ok, 'message' => $message], JSON_UNESCAPED_UNICODE);
    exit;
}

function header_text(string $s): string
{
    return '=?UTF-8?B?' . base64_encode($s) . '?=';
}

function clean_line(string $s): string
{
    return trim(preg_replace('/[\r\n\t]+/', ' ', $s));
}

function esc(string $s): string
{
    return htmlspecialchars($s, ENT_QUOTES, 'UTF-8');
}

// Письмо: текст + HTML + вложения
function send_mail(string $to, string $subject, string $text, ?string $html, array $files, string $replyTo): bool
{
    $mixed = 'mixed_' . bin2hex(random_bytes(12));
    $alt = 'alt_' . bin2hex(random_bytes(12));

    $headers = [
        'From: ' . header_text(FROM_NAME) . ' <' . MAIL_FROM . '>',
        'Reply-To: ' . $replyTo,
        'MIME-Version: 1.0',
        'Content-Type: multipart/mixed; boundary="' . $mixed . '"',
    ];

    $body = '--' . $mixed . "\r\n";
    if ($html !== null) {
        $body .= 'Content-Type: multipart/alternative; boundary="' . $alt . "\"\r\n\r\n";
        $body .= '--' . $alt . "\r\n" . "Content-Type: text/plain; charset=UTF-8\r\nContent-Transfer-Encoding: base64\r\n\r\n";
        $body .= chunk_split(base64_encode($text)) . "\r\n";
        $body .= '--' . $alt . "\r\n" . "Content-Type: text/html; charset=UTF-8\r\nContent-Transfer-Encoding: base64\r\n\r\n";
        $body .= chunk_split(base64_encode($html)) . "\r\n";
        $body .= '--' . $alt . "--\r\n";
    } else {
        $body .= "Content-Type: text/plain; charset=UTF-8\r\nContent-Transfer-Encoding: base64\r\n\r\n";
        $body .= chunk_split(base64_encode($text)) . "\r\n";
    }

    foreach ($files as $f) {
        $name = $f['name'];
        $ascii = preg_replace('/[^A-Za-z0-9._-]/', '_', $name);
        $body .= '--' . $mixed . "\r\n";
        $body .= 'Content-Type: application/octet-stream; name="' . $ascii . "\"\r\n";
        $body .= "Content-Transfer-Encoding: base64\r\n";
        $body .= 'Content-Disposition: attachment; filename="' . $ascii . "\"; filename*=UTF-8''" . rawurlencode($name) . "\r\n\r\n";
        $body .= chunk_split(base64_encode($f['data'])) . "\r\n";
    }
    $body .= '--' . $mixed . "--\r\n";

    return mail($to, header_text($subject), $body, implode("\r\n", $headers), '-f' . MAIL_FROM);
}

if (($_SERVER['REQUEST_METHOD'] ?? '') !== 'POST') {
    reply(405, false, 'Method not allowed');
}

// Принимаем заявки только со своего сайта
$source = $_SERVER['HTTP_ORIGIN'] ?? ($_SERVER['HTTP_REFERER'] ?? '');
if (!preg_match('~^https://(www\.)?promoznachki\.ru(/|$)~', $source)) {
    reply(403, false, 'Forbidden');
}

// Слишком большой запрос: PHP уже отбросил поля
if (empty($_POST) && (int)($_SERVER['CONTENT_LENGTH'] ?? 0) > 0) {
    reply(413, false, 'Файлы слишком большие: всего до 10 МБ');
}

// Бот заполнил скрытое поле — делаем вид, что всё хорошо
if (!empty($_POST['_honey'])) {
    reply(200, true);
}

// Ограничение частоты
$ip = $_SERVER['REMOTE_ADDR'] ?? 'unknown';
$rateDir = dirname(__DIR__, 2) . '/tmp-forms';
if (!is_dir($rateDir)) {
    @mkdir($rateDir, 0700, true);
}
$rateFile = $rateDir . '/' . md5($ip) . '.json';
$now = time();
$hits = [];
if (is_file($rateFile)) {
    $hits = json_decode((string)file_get_contents($rateFile), true) ?: [];
}
$hits = array_values(array_filter($hits, static fn($t) => is_int($t) && $t > $now - RATE_WINDOW));
if (count($hits) >= RATE_LIMIT) {
    reply(429, false, 'Слишком много заявок подряд. Попробуйте через несколько минут.');
}

// Поля формы (PHP заменяет пробелы в именах полей на «_»)
$fields = [];
foreach ($_POST as $key => $value) {
    if (!is_string($key) || !is_string($value) || $key === '' || $key[0] === '_' || count($fields) >= 20) {
        continue;
    }
    $label = mb_substr(str_replace('_', ' ', $key), 0, 60);
    $fields[$label] = mb_substr(trim($value), 0, 5000);
}

$name = clean_line($fields['Имя'] ?? '');
$phone = clean_line($fields['Телефон'] ?? '');
$email = clean_line($fields['email'] ?? '');
$request = $fields['Запрос'] ?? '';
$digits = preg_replace('/\D/', '', $phone);

if (mb_strlen($name) < 2 || strlen($digits) < 10 || strlen($digits) > 12
    || !filter_var($email, FILTER_VALIDATE_EMAIL) || mb_strlen($request) < 5) {
    reply(422, false, 'Заполните имя, телефон, почту и запрос');
}

// Спам: ссылки, html, стоп-слова — отвечаем «успехом», но не отправляем
$text = mb_strtolower($name . ' ' . $request);
$spam = preg_match_all('~https?://|www\.~i', $text) > 1 || preg_match('/<[a-z][\s\S]*>/i', $text);
foreach (STOP_WORDS as $word) {
    if (mb_strpos($text, $word) !== false) {
        $spam = true;
    }
}
if ($spam) {
    reply(200, true);
}

// Вложения
$files = [];
$total = 0;
if (isset($_FILES['attachment']) && is_array($_FILES['attachment']['name'])) {
    $up = $_FILES['attachment'];
    foreach ($up['name'] as $i => $fileName) {
        if ($up['error'][$i] === UPLOAD_ERR_NO_FILE) {
            continue;
        }
        if ($up['error'][$i] !== UPLOAD_ERR_OK || !is_uploaded_file($up['tmp_name'][$i])) {
            reply(400, false, 'Не удалось загрузить файл ' . clean_line((string)$fileName));
        }
        $fileName = clean_line(basename((string)$fileName));
        $ext = strtolower(pathinfo($fileName, PATHINFO_EXTENSION));
        if (!in_array($ext, ALLOWED, true)) {
            reply(400, false, 'Этот тип файла не поддерживается: ' . $fileName);
        }
        $total += (int)$up['size'][$i];
        if (count($files) >= MAX_FILES || $total > MAX_TOTAL) {
            reply(400, false, 'Можно прикрепить до 5 файлов, всего до 10 МБ');
        }
        $files[] = ['name' => $fileName, 'data' => (string)file_get_contents($up['tmp_name'][$i])];
    }
}
$fileNames = array_column($files, 'name');

// Письмо в отдел продаж
$rows = '';
$plain = '';
foreach ($fields as $label => $value) {
    if ($value === '') {
        continue;
    }
    $rows .= '<tr><td style="padding:8px 12px;border:1px solid #ddd;background:#f6f6f6;font-weight:bold;vertical-align:top;white-space:nowrap">'
        . esc($label) . '</td><td style="padding:8px 12px;border:1px solid #ddd">' . nl2br(esc($value)) . '</td></tr>';
    $plain .= $label . ': ' . $value . "\n\n";
}
if ($fileNames) {
    $rows .= '<tr><td style="padding:8px 12px;border:1px solid #ddd;background:#f6f6f6;font-weight:bold">Файлы</td><td style="padding:8px 12px;border:1px solid #ddd">'
        . esc(implode(', ', $fileNames)) . '</td></tr>';
    $plain .= 'Файлы: ' . implode(', ', $fileNames) . "\n\n";
}
$page = clean_line($_SERVER['HTTP_REFERER'] ?? 'https://promoznachki.ru/');
$html = '<div style="font-family:Arial,sans-serif;font-size:14px;color:#222">'
    . '<p>Новая заявка с сайта promoznachki.ru</p>'
    . '<table style="border-collapse:collapse">' . $rows . '</table>'
    . '<p style="color:#888;font-size:12px">Страница: ' . esc($page) . '<br>Отправлено: ' . date('d.m.Y H:i') . ' (МСК)</p></div>';
$plain = "Новая заявка с сайта promoznachki.ru\n\n" . $plain . 'Страница: ' . $page;

$replyTo = header_text($name) . ' <' . $email . '>';
if (!send_mail(MAIL_TO, SUBJECT_SALES, $plain, $html, $files, $replyTo)) {
    reply(500, false, 'Не удалось отправить');
}

$hits[] = $now;
@file_put_contents($rateFile, json_encode($hits), LOCK_EX);

// Подтверждение клиенту с составом заявки
$confirm = implode("\n", array_merge(
    [
        'Здравствуйте, ' . $name . '!',
        '',
        'Спасибо за заявку на сайте promoznachki.ru. Мы её получили, в ближайшее время обработаем и свяжемся с вами (по будням с 10:00 до 19:00).',
        '',
        'Состав заявки:',
        preg_replace('/^Хочу заказать:\s*/u', '', trim($request)),
    ],
    $fileNames ? ['', 'Прикреплённые файлы: ' . implode(', ', $fileNames)] : [],
    [
        '',
        'Если нужно что-то уточнить или добавить, напишите на sales@promoznachki.ru или позвоните: +7 (499) 394-59-84, +7 (926) 676-44-35.',
        '',
        'С уважением, команда «ПромоЗначки»',
        'https://promoznachki.ru',
    ]
));
send_mail($email, SUBJECT_CLIENT, $confirm, null, [], header_text(FROM_NAME) . ' <' . MAIL_FROM . '>');

reply(200, true);
