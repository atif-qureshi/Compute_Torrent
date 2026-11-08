"""Real Tk widget tests, isolated from provider networking and updater services."""
import ast
from pathlib import Path
import subprocess
import sys
import unittest
import customtkinter as ctk
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'08-provider-node/05-desktop-app-shell'))
import provider_views as view
from production_seeder import ComputeTorrentSeeder

class Fixture(ctk.CTk):
    render_resources=ComputeTorrentSeeder.render_resources
    render_connection_state=ComputeTorrentSeeder.render_connection_state
    update_work_history=ComputeTorrentSeeder.update_work_history
    def __init__(self):
        super().__init__();self.withdraw();self.geometry('1120x850')
        self.profile=dict(cpu_cores=8,physical_cores=4,RAM=16,free_ram_gb=9,GPU=None,VRAM=0,CUDA=False,docker_ok=True,petals_image_ready=True,cpu_model='Fixture CPU',disk_free_gb=80)
        self.cpu_limit=2;self.memory_limit_gb=8;self.petals_enabled=True;self.orchestrator_url='ws://127.0.0.1:8001/ws/seeder';self.enrollment_token='fixture-secret';self.connection_note='Fixture connection detail';self.node_id='fixture-node';self.connection_state='Registered';self.is_connected=True;self.paused=False;self.tasks_completed=3;self.credits_earned=2;self.recent_work=[];self.shutting_down=False;self.actions=[];self.settings={}
    def clear_screen(self):
        for child in self.winfo_children(): child.destroy()
    def save_settings(self):self.actions.append('save-settings')
    def start_connection(self):self.actions.append('connect')
    def disconnect_provider(self):self.actions.append('disconnect')
    def install_petals_runtime(self,device):self.actions.append(device)
    def refresh_hardware_profile(self):self.actions.append('hardware')
    def toggle_pause(self):self.actions.append('pause')

def widgets(parent):
    for child in parent.winfo_children():
        yield child
        yield from widgets(child)

def invoke(app,text):
    matches=[w for w in widgets(app) if isinstance(w,ctk.CTkButton) and w.cget('text')==text]
    assert len(matches)==1,(text,len(matches))
    matches[0].invoke()

class ProviderViewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=Fixture()
    @classmethod
    def tearDownClass(cls):cls.app.destroy()
    def setUp(self):
        self.app.actions=[]
        self.app.is_connected=True
        self.app.connection_state='Registered'
        self.app.profile['CUDA']=False
    def tearDown(self):
        self.app.update()
        self.app.clear_screen()
    def test_setup_widgets_and_callbacks(self):
        view.onboarding(self.app);self.app.update_idletasks()
        self.assertEqual(self.app.server_entry.get(),self.app.orchestrator_url)
        self.assertEqual(self.app.enrollment_entry.cget('show'),'•')
        self.assertEqual(self.app.cpu_entry.get(),'2');self.assertEqual(self.app.memory_entry.get(),'8')
        self.assertEqual(self.app.layer_switch.get(),1)
        invoke(self.app,'Connect to workspace');invoke(self.app,'Prepare CPU runtime');invoke(self.app,'Refresh hardware detection')
        self.assertEqual(self.app.actions,['connect','cpu','hardware'])
    def test_dashboard_uses_confirmed_registration_and_retains_all_live_targets(self):
        view.dashboard(self.app);self.app.update()
        self.assertEqual(self.app.connection_badge.cget('text'),'Registered')
        for attr in ['status_label','layer_label','task_label','cpu_detail','memory_detail','gpu_detail','docker_detail','count_label','credits_label','history_box','pause_btn']:
            self.assertTrue(getattr(self.app,attr).winfo_exists(),attr)
        self.app.is_connected=False;self.app.render_connection_state()
        self.assertEqual(self.app.connection_badge.cget('text'),'Reconnecting')
        invoke(self.app,'Disconnect');self.app.pause_btn.invoke();self.assertEqual(self.app.actions,['disconnect','pause'])
    def test_navigation_keeps_widgets_alive_and_shows_requested_page(self):
        view.onboarding(self.app);self.app.update_idletasks()
        self.app.server_entry.delete(0,'end');self.app.server_entry.insert(0,'unsaved-address')
        invoke(self.app,'Hardware');self.assertEqual(self.app._provider_page,'Hardware')
        invoke(self.app,'Connection');self.assertEqual(self.app.server_entry.get(),'unsaved-address')
        invoke(self.app,'Help');self.assertEqual(self.app._provider_page,'Help')
    def test_only_selected_page_is_mapped_and_setup_is_visible_on_launch(self):
        self.app._provider_page='Connection'
        view.onboarding(self.app);self.app.deiconify();self.app.update()
        help_title=next(w for w in widgets(self.app) if isinstance(w,ctk.CTkLabel) and w.cget('text')=='Help')
        self.assertTrue(self.app.server_entry.winfo_viewable())
        self.assertFalse(help_title.winfo_viewable(),'Help must not cover Connection')
        self.app.server_entry.insert('end','-unsaved')
        for name in ['Hardware','Help','Connection']:
            invoke(self.app,name);self.app.update()
            self.assertEqual(bool(self.app.server_entry.winfo_viewable()),name=='Connection')
            self.assertEqual(bool(help_title.winfo_viewable()),name=='Help')
        self.assertTrue(self.app.server_entry.get().endswith('-unsaved'))
        self.app.withdraw()
    def test_overview_reflows_side_by_side_without_replacing_live_controls(self):
        self.app._provider_page='Overview'
        view.dashboard(self.app);self.app.deiconify()
        controls=[self.app.connection_badge,self.app.cpu_detail,self.app.task_label]
        for width,columns in [(1700,2),(1120,2),(960,2),(800,1),(1700,2)]:
            self.app.geometry(f'{width}x850');self.app.update()
            self.assertEqual(self.app.overview_grid.columns,columns)
            cards=self.app.overview_grid.cards
            if columns==2:
                self.assertEqual(cards[0].winfo_y(),cards[1].winfo_y())
                self.assertLess(cards[0].winfo_x(),cards[1].winfo_x())
                self.assertLessEqual(abs(cards[0].winfo_width()-cards[1].winfo_width()),2)
                self.assertGreater(cards[2].winfo_y(),cards[0].winfo_y())
                self.assertEqual(cards[2].winfo_x(),cards[0].winfo_x())
                self.assertEqual(int(cards[2].grid_info()['columnspan']),2)
                self.assertGreater(cards[2].winfo_width(),cards[0].winfo_width()*1.9)
                self.assertLessEqual(cards[2].winfo_rootx()+cards[2].winfo_width(),self.app.winfo_rootx()+self.app.winfo_width())
            self.assertTrue(all(w.winfo_exists() for w in controls))
        self.app.withdraw();self.app.geometry('1120x850')
    def test_hardware_redraw_preserves_unsaved_layer_choice_and_navigation(self):
        view.onboarding(self.app)
        self.app.layer_switch.deselect()
        invoke(self.app,'Hardware')
        ComputeTorrentSeeder.show_onboarding(self.app)
        self.assertEqual(self.app.layer_switch.get(),0)
        self.assertEqual(self.app._provider_page,'Hardware')
    def test_theme_switch_preserves_fields_and_saves_preference(self):
        view.onboarding(self.app)
        self.app.server_entry.insert('end','-unsaved')
        callback=self.app.appearance_menu.cget('command')
        for mode in ['Dark','Light','System']:
            callback(mode);self.app.update_idletasks()
            self.assertEqual(self.app.settings['appearance'],mode)
            self.assertTrue(self.app.server_entry.get().endswith('-unsaved'))
        self.assertEqual(self.app.actions,['save-settings']*3)
    def test_no_gpu_does_not_offer_cuda_runtime(self):
        view.onboarding(self.app)
        self.assertFalse(any(isinstance(w,ctk.CTkButton) and w.cget('text')=='Prepare CUDA runtime' for w in widgets(self.app)))
    def test_minimum_window_fits_connection_fields_and_cuda_action(self):
        self.app.geometry('960x680')
        self.app.profile['CUDA']=True
        view.onboarding(self.app)
        self.app.deiconify();self.app.update()
        left=self.app.winfo_rootx();right=left+self.app.winfo_width()
        self.assertGreater(self.app.server_entry.winfo_width(),300)
        self.assertGreaterEqual(self.app.server_entry.winfo_rootx(),left)
        self.assertLessEqual(self.app.server_entry.winfo_rootx()+self.app.server_entry.winfo_width(),right)
        invoke(self.app,'Prepare CUDA runtime');self.assertEqual(self.app.actions,['cuda'])
        self.app.withdraw();self.app.geometry('1120x850')
    def test_notification_colors_are_legible_without_changing_message(self):
        label=view.NoticeLabel(self.app,text='Original update message');label.configure(text_color='#86efac')
        self.assertEqual(label.cget('text_color'),view.GREEN);self.assertEqual(label.cget('text'),'Original update message')
    def test_mirror_matches_and_updater_methods_unchanged(self):
        path=Path('08-provider-node/05-desktop-app-shell/production_seeder.py')
        current=ast.parse((ROOT/path).read_text(encoding='utf-8-sig'))
        baseline=ast.parse(subprocess.check_output(['git','show','HEAD:'+path.as_posix()],cwd=ROOT).decode('utf-8-sig'))
        def methods(tree):return {n.name:ast.dump(n,include_attributes=False) for cls in tree.body if isinstance(cls,ast.ClassDef) for n in cls.body if isinstance(n,ast.FunctionDef)}
        old,new=methods(baseline),methods(current)
        for name in ['check_for_update','_set_update_ui','_show_progress_banner','_hide_progress_banner','_update_progress','update_clicked','start_connection','disconnect_provider','toggle_pause','save_settings']:
            self.assertEqual(old[name],new[name],name)
        for file in ['production_seeder.py','provider_views.py']:
            self.assertEqual((ROOT/'08-provider-node/05-desktop-app-shell'/file).read_bytes(),(ROOT/'desktop/05-desktop-app-shell'/file).read_bytes())

if __name__=='__main__':unittest.main()
