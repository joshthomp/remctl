"""Saved preview decoding stays local, bounded and independent of Objective-C classes."""
import plistlib
import sqlite3
import unittest
from unittest.mock import patch
import socket
from remctl_workspace import decode_link_archive, rich_link_rows, saved_link_preview, fetch_public_bytes, fetch_public_preview

class RichPreviewTests(unittest.TestCase):
    def test_apple_archive_resolves_shared_values_without_executing_classes(self):
        uid = plistlib.UID
        image = b'\x89PNG\r\n\x1a\n' + b'hero'
        icon = b'\xff\xd8\xfficon'
        raw = plistlib.dumps({'$archiver':'NSKeyedArchiver', '$top':{'root':uid(1)}, '$objects':[
            '$null', {'title':uid(2),'image':uid(3),'icon':uid(4),'URL':uid(5)}, 'A saved page',
            {'data':uid(6)}, {'data':uid(7)}, {'NS.relative':uid(8)}, image, icon, 'https://example.com/saved']}, fmt=plistlib.FMT_BINARY)
        result = saved_link_preview('https://example.com/saved', raw)
        self.assertEqual(result['title'], 'A saved page')
        self.assertEqual(result['domain'], 'example.com')
        self.assertEqual(result['image']['mimeType'], 'image/png')
        self.assertEqual(result['icon']['mimeType'], 'image/jpeg')

    def test_missing_corrupt_cyclic_and_untrusted_archive_is_a_plain_card(self):
        for raw in [None,b'not a plist',b'x'*(16*1024*1024+1),plistlib.dumps({'$top':{'root':plistlib.UID(1)},'$objects':['$null',{'image':plistlib.UID(1)}]},fmt=plistlib.FMT_BINARY)]:
            result = saved_link_preview('https://example.com', raw)
            self.assertNotIn('image',result)
            self.assertEqual(result['url'],'https://example.com')
        raw=plistlib.dumps({'title':'Stored title','image':'https://tracking.invalid/image.png'})
        self.assertNotIn('image',saved_link_preview('https://example.com',raw))

    def test_query_is_scoped_to_reminder_and_excludes_deleted_links(self):
        db=sqlite3.connect(':memory:');db.row_factory=sqlite3.Row
        db.execute('CREATE TABLE ZREMCDOBJECT (Z_PK INTEGER,ZREMINDER2 INTEGER,ZURL TEXT,ZMETADATA BLOB,ZMARKEDFORDELETION INTEGER)')
        db.executemany('INSERT INTO ZREMCDOBJECT VALUES (?,?,?,?,?)',[(1,42,'https://example.com',b'preview',0),(2,99,'https://other.com',None,0),(3,42,'https://deleted.com',None,1)])
        self.assertEqual([r['ZURL'] for r in rich_link_rows(db,42)],['https://example.com'])
        db.close()

    def test_public_previews_reject_private_addresses_before_connecting(self):
        for address in ('127.0.0.1','10.0.0.1','169.254.169.254','100.64.0.1','::1'):
            with patch('socket.getaddrinfo', return_value=[(socket.AF_INET,socket.SOCK_STREAM,6,'',(address,443))]), patch('socket.socket') as connect:
                with self.assertRaises(ValueError): fetch_public_bytes('https://example.com',100)
                connect.assert_not_called()
        with self.assertRaises(ValueError): fetch_public_bytes('https://user:password@example.com',100)

    def test_metadata_fallback_fetches_only_bounded_declared_artwork(self):
        page = b'<html><meta property="og:title" content="Real title"><meta property="og:image" content="/hero.png"><script>ignored()</script></html>'
        image = b'\x89PNG\r\n\x1a\nreal-image'
        with patch('remctl_workspace.fetch_public_bytes', side_effect=[(page,'text/html','https://example.com/page'),(image,'image/png','https://example.com/hero.png')]) as fetch:
            result=fetch_public_preview('https://example.com/page')
            self.assertEqual(result['title'],'Real title')
            self.assertEqual(result['image']['mimeType'],'image/png')
            self.assertEqual(fetch.call_args_list[1].args,('https://example.com/hero.png',4*1024*1024))

if __name__ == '__main__':unittest.main()
